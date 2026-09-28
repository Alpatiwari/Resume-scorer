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
from datetime import datetime, timezone
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

from app.celery_app import celery_app
from app.config import ALLOW_DEGRADED_SCORING, GEMINI_MODEL, PARSE_SOFT_TIME_LIMIT_SECONDS, SCORING_CONCURRENCY
from app.database import SessionLocal
from app.models.db_models import JobModel, JobResumeModel, ResumeModel, ScoreModel
from app.models.resume import ResumeStatus
from app.services.nlp_extractor import JobRequirements, ResumeProfile, extract_job_requirements, extract_resume_profile
from app.services.parser import EmptyResumeError, UnsupportedFileTypeError, extract_text
from app.services.scorer import score_resume


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short(text: str | None, limit: int = 300) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _mark_failed(record: ResumeModel, message: str) -> None:
    record.status = ResumeStatus.failed.value
    record.error = message[:500]
    record.status_changed_at = _now()


@celery_app.task(name="app.workers.process_resume", soft_time_limit=PARSE_SOFT_TIME_LIMIT_SECONDS)
def process_resume(resume_id: str, file_path: str) -> None:
    """Extracts text from a saved resume file and updates its DB record.
    Runs in the Celery worker process, so it needs its own DB session —
    it can't reuse the one from the request that queued it.

    Whatever goes wrong, the record ends up "parsed" or "failed" with a
    reason. It never stays in a working state (see also
    services/resume_status.py for the safety net if this process dies)."""
    db = SessionLocal()
    try:
        record = db.get(ResumeModel, resume_id)
        if not record:
            return  # resume was deleted before the task ran

        record.status = ResumeStatus.parsing.value
        record.error = None
        record.status_changed_at = _now()
        db.commit()

        try:
            text = extract_text(Path(file_path))
        except (UnsupportedFileTypeError, EmptyResumeError) as e:
            _mark_failed(record, str(e))
            db.commit()
            return

        # Extract the resume profile (skills/experience/education/etc)
        # once, here, at parse time — it doesn't depend on any job
        # description, so scoring can reuse it instead of paying for
        # a fresh Gemini extraction call every time this resume is
        # scored. Best-effort: if it fails, parsing still succeeds
        # and scoring will just fall back to extracting on the fly.
        profile = None
        profile_warning = None
        try:
            profile = extract_resume_profile(text)
            profile_warning = profile.llm_error  # AI pass failed, regex-only profile
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            logger.warning("Profile extraction failed for resume %s", resume_id, exc_info=True)
            profile_warning = f"{type(e).__name__}: {e}"

        # Parsing still succeeds, but the reason is stored so the UI can say
        # "keyword matching only" instead of the recruiter never knowing.
        record.profile_warning = _short(profile_warning) if profile_warning else None
        record.extracted_text = text
        if profile is not None:
            record.profile_skills = profile.skills
            record.profile_experience_years = profile.experience_years
            record.profile_education = profile.education
            record.profile_projects = profile.projects
            record.profile_red_flags = profile.red_flags
        record.status = ResumeStatus.parsed.value
        record.error = None
        record.status_changed_at = _now()
        db.commit()
    except Exception as e:  # corrupt file, encrypted PDF, timeout, DB hiccup, ...
        db.rollback()
        logger.exception("Processing failed for resume %s", resume_id)
        if isinstance(e, SoftTimeLimitExceeded):
            message = f"Processing took longer than {PARSE_SOFT_TIME_LIMIT_SECONDS}s and was stopped."
        else:
            message = (
                f"Could not read this file ({type(e).__name__}). "
                "It may be corrupt or password-protected."
            )
        try:
            record = db.get(ResumeModel, resume_id)
            if record:
                _mark_failed(record, message)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not record the failure for resume %s", resume_id)
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
    """Scores every parsed resume in THIS job's batch against its job description.

    Runs the (up to) two Gemini calls per resume across a small thread
    pool (SCORING_CONCURRENCY workers) instead of one at a time, and each
    call is bounded by GEMINI_TIMEOUT_MS, so one slow resume can't stall
    the whole batch. Progress is written to JobModel.scoring_done/total
    as each resume finishes, so the frontend can poll instead of holding
    one long request open.

    Existing scores are NOT deleted up front. New results are collected in
    memory and written in a single transaction at the end, updating rows in
    place. So a crash mid-run leaves the previous results intact, and
    shortlist/stage decisions survive a re-score.
    """
    db = SessionLocal()
    job = None
    try:
        job = db.get(JobModel, job_id)
        if not job:
            return

        resumes = (
            db.query(ResumeModel)
            .join(JobResumeModel, JobResumeModel.resume_id == ResumeModel.id)
            .filter(JobResumeModel.job_id == job_id, ResumeModel.status == ResumeStatus.parsed.value)
            .all()
        )

        job.scoring_status = "running"
        job.scoring_total = len(resumes)
        job.scoring_done = 0
        job.scoring_error = None
        job.scoring_heartbeat_at = _now()
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
                    llm_error=r.profile_warning,
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

        results: dict[str, tuple[str, object]] = {}  # resume_id -> (filename, ScoreResult)
        done = 0
        failed = 0
        last_error = None
        with ThreadPoolExecutor(max_workers=SCORING_CONCURRENCY) as pool:
            futures = {pool.submit(_score_one, rd): rd for rd in resume_data}
            for future in as_completed(futures):
                rd = futures[future]
                try:
                    _, result = future.result()
                    results[rd["id"]] = (rd["filename"], result)
                except Exception as e:
                    # One resume failing shouldn't sink the whole batch —
                    # but it must be logged, or a batch where every resume
                    # fails silently reports "done" with nothing to show.
                    # Its previous score row (if any) is left untouched.
                    logger.exception(
                        "Scoring failed for resume %s (%s) in job %s",
                        rd["id"], rd["filename"], job_id,
                    )
                    failed += 1
                    last_error = f"{rd['filename']}: {e}"

                done += 1
                job.scoring_done = done
                job.scoring_heartbeat_at = _now()
                db.commit()

        # If Gemini failed for EVERY scored resume, the most likely cause is a
        # wrong model name / bad key / no network. Saving those scores would
        # produce a ranking with no LLM judgment in it and no obvious reason,
        # so fail loudly and leave the previous results untouched.
        llm_down = [res for _, res in results.values() if res.llm_unavailable]
        if results and len(llm_down) == len(results) and not ALLOW_DEGRADED_SCORING:
            job.scoring_status = "failed"
            job.scoring_error = (
                f"AI judgment failed for all {len(results)} resume(s) (model '{GEMINI_MODEL}'), "
                f"so no scores were saved. First error: {_short(llm_down[0].llm_error)} "
                "Check GET /api/health/llm, or set RESUME_SCORER_ALLOW_DEGRADED_SCORING=true "
                "to save keyword/semantic-only scores."
            )
            job.scoring_heartbeat_at = _now()
            db.commit()
            return

        # Only now touch the scores table, all in one transaction.
        existing = {s.resume_id: s for s in db.query(ScoreModel).filter(ScoreModel.job_id == job_id)}
        scored_at = _now()
        for resume_id, (filename, result) in results.items():
            row = existing.get(resume_id)
            if row is None:
                row = ScoreModel(job_id=job_id, resume_id=resume_id)
                db.add(row)
            # shortlisted / stage are deliberately not touched here.
            row.filename = filename
            row.final_score = result.final_score
            row.skill_overlap_score = result.skill_overlap_score
            row.embedding_score = result.embedding_score
            row.llm_score = result.llm_score
            row.matched_skills = result.matched_skills
            row.missing_skills = result.missing_skills
            row.red_flags = result.red_flags
            row.reasoning = result.reasoning
            row.score_warnings = result.warnings
            row.scored_at = scored_at

        # "done" can still carry notes; the frontend shows scoring_error
        # whenever it is set, so a degraded run is never silent.
        notes = []
        if failed:
            notes.append(f"{failed} of {len(resume_data)} resume(s) failed to score. Last error: {last_error}")
        if llm_down:
            notes.append(
                f"AI judgment was unavailable for {len(llm_down)} of {len(results)} scored resume(s); "
                "their scores use keyword/semantic methods only and are flagged in the breakdown. "
                f"First error: {_short(llm_down[0].llm_error)}"
            )
        embed_down = sum(1 for _, res in results.values() if res.embedding_score is None)
        if embed_down:
            notes.append(f"Semantic similarity failed for {embed_down} resume(s); it was left out of their scores.")

        if failed and failed == len(resume_data):
            job.scoring_status = "failed"
            job.scoring_error = f"All {failed} resume(s) failed to score. Last error: {last_error}"
        else:
            job.scoring_status = "done"
            job.scoring_error = " ".join(notes) or None
        job.scoring_heartbeat_at = _now()
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Scoring run crashed for job %s", job_id)
        if job is not None:
            job.scoring_status = "failed"
            job.scoring_error = str(e)
            db.commit()
    finally:
        db.close()
