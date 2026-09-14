"""
Background tasks for resume processing. This is what makes bulk upload
non-blocking: the upload endpoint saves the file and enqueues a task
here instead of calling extract_text() inline.

Scoring lives here too (score_job below) for the same reason: hitting
Gemini twice per resume for 100+ resumes takes real wall-clock time, and
that work belongs in a worker, not blocking an HTTP request / FastAPI's
event loop.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

from app.celery_app import celery_app
from app.config import SCORING_CONCURRENCY
from app.database import SessionLocal
from app.models.db_models import JobModel, ResumeModel, ScoreModel
from app.models.resume import ResumeStatus
from app.services.nlp_extractor import JobRequirements, ResumeProfile, extract_job_requirements, extract_resume_profile
from app.services.parser import EmptyResumeError, UnsupportedFileTypeError, extract_text
from app.services.scorer import score_resume


@celery_app.task(name="app.workers.process_resume")
def process_resume(resume_id: str, file_path: str) -> None:
    """Extracts text from a saved resume file and updates its DB record.
    Runs in the Celery worker process, so it needs its own DB session —
    it can't reuse the one from the request that queued it."""
    db = SessionLocal()
    try:
        record = db.get(ResumeModel, resume_id)
        if not record:
            return  # resume was deleted before the task ran

        try:
            text = extract_text(Path(file_path))
            record.status = ResumeStatus.parsed.value
            record.extracted_text = text
            record.error = None

            # Extract the resume profile (skills/experience/education/etc)
            # once, here, at parse time — it doesn't depend on any job
            # description, so scoring can reuse it instead of paying for
            # a fresh Gemini extraction call every time this resume is
            # scored. Best-effort: if it fails, parsing still succeeds
            # and scoring will just fall back to extracting on the fly.
            try:
                profile = extract_resume_profile(text)
                record.profile_skills = profile.skills
                record.profile_experience_years = profile.experience_years
                record.profile_education = profile.education
                record.profile_projects = profile.projects
                record.profile_red_flags = profile.red_flags
            except Exception:
                pass
        except (UnsupportedFileTypeError, EmptyResumeError) as e:
            record.status = ResumeStatus.failed.value
            record.error = str(e)

        db.commit()
    finally:
        db.close()


def _requirements_from_job(job: JobModel) -> JobRequirements:
    return JobRequirements(
        required_skills=job.required_skills,
        nice_to_have_skills=job.nice_to_have_skills,
        min_experience_years=job.min_experience_years,
    )


@celery_app.task(name="app.workers.score_job")
def score_job(job_id: str) -> None:
    """Scores every parsed resume against a job description.

    Runs the (up to) two Gemini calls per resume across a small thread
    pool (SCORING_CONCURRENCY workers) instead of one at a time, and each
    call is bounded by GEMINI_TIMEOUT_MS, so one slow resume can't stall
    the whole batch. Progress is written to JobModel.scoring_done/total
    as each resume finishes, so the frontend can poll instead of holding
    one long request open.
    """
    db = SessionLocal()
    job = None
    try:
        job = db.get(JobModel, job_id)
        if not job:
            return

        resumes = db.query(ResumeModel).filter(ResumeModel.status == ResumeStatus.parsed.value).all()

        job.scoring_status = "running"
        job.scoring_total = len(resumes)
        job.scoring_done = 0
        job.scoring_error = None
        db.commit()

        if not resumes:
            job.scoring_status = "done"
            db.commit()
            return

        requirements = (
            _requirements_from_job(job) if job.required_skills
            else extract_job_requirements(job.description)
        )
        job_description = job.description 
        db.query(ScoreModel).filter(ScoreModel.job_id == job_id).delete()
        db.commit()

        # Snapshot plain data for the worker threads up front — SQLAlchemy
        # ORM objects/sessions aren't safe to share across threads. Reuse
        # the profile captured at parse time when we have one, so scoring
        # doesn't pay for a second Gemini extraction call per resume.
        resume_data = [
            {
                "id": r.id,
                "filename": r.filename,
                "text": r.extracted_text or "",
                "profile": ResumeProfile(
                    skills=r.profile_skills or [],
                    experience_years=r.profile_experience_years,
                    education=r.profile_education or [],
                    projects=r.profile_projects or [],
                    red_flags=r.profile_red_flags or [],
                ) if r.profile_skills else None,
            }
            for r in resumes
        ]

        def _score_one(rd: dict):
            return rd, score_resume(
                resume_id=rd["id"],
                resume_text=rd["text"],
                job_text=job_description,
                job_requirements=requirements,
                resume_profile=rd["profile"],
            )

        done = 0
        failed = 0
        last_error = None
        with ThreadPoolExecutor(max_workers=SCORING_CONCURRENCY) as pool:
            futures = {pool.submit(_score_one, rd): rd for rd in resume_data}
            for future in as_completed(futures):
                rd = futures[future]
                try:
                    _, result = future.result()
                    db.add(ScoreModel(
                        job_id=job_id, resume_id=result.resume_id, filename=rd["filename"],
                        final_score=result.final_score, skill_overlap_score=result.skill_overlap_score,
                        embedding_score=result.embedding_score, llm_score=result.llm_score,
                        matched_skills=result.matched_skills, missing_skills=result.missing_skills,
                        red_flags=result.red_flags, reasoning=result.reasoning,
                    ))
                except Exception as e:
                    # One resume failing (e.g. a Gemini timeout that
                    # somehow still raised) shouldn't sink the whole batch —
                    # but it must be logged, or a batch where every resume
                    # fails silently reports "done" with nothing to show.
                    logger.exception(
                        "Scoring failed for resume %s (%s) in job %s",
                        rd["id"], rd["filename"], job_id,
                    )
                    failed += 1
                    last_error = f"{rd['filename']}: {e}"

                done += 1
                job.scoring_done = done
                db.commit()

        if failed and failed == len(resume_data):
            job.scoring_status = "failed"
            job.scoring_error = f"All {failed} resume(s) failed to score. Last error: {last_error}"
        elif failed:
            job.scoring_status = "done"
            job.scoring_error = f"{failed} of {len(resume_data)} resume(s) failed to score. Last error: {last_error}"
        else:
            job.scoring_status = "done"
        db.commit()
    except Exception as e:
        if job is not None:
            job.scoring_status = "failed"
            job.scoring_error = str(e)
            db.commit()
    finally:
        db.close()