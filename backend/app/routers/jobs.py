import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import SCORING_STALE_MINUTES
from app.database import get_db
from app.models.db_models import JobModel, JobResumeModel, ResumeModel, ScoreModel
from app.services.resume_status import expire_stale_parses
from app.services.nlp_extractor import extract_job_requirements

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobDescriptionIn(BaseModel):
    title: str
    description: str
    experience: str | None = None


class JobDescriptionOut(JobDescriptionIn):
    id: str
    created_at: datetime
    required_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    min_experience_years: float | None = None
    # Not stored: set on create when AI extraction failed (keyword-only skills).
    extraction_warning: str | None = None

    class Config:
        from_attributes = True


@router.post("", response_model=JobDescriptionOut)
async def create_job(job: JobDescriptionIn, db: Session = Depends(get_db)):
    job_id = str(uuid.uuid4())
    requirements = extract_job_requirements(job.description)

    record = JobModel(
        id=job_id,
        title=job.title,
        description=job.description,
        experience=job.experience,
        created_at=datetime.now(timezone.utc),
        required_skills=requirements.required_skills,
        nice_to_have_skills=requirements.nice_to_have_skills,
        min_experience_years=requirements.min_experience_years,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    out = JobDescriptionOut.model_validate(record)
    out.extraction_warning = requirements.llm_error
    return out


@router.get("")
async def list_jobs(db: Session = Depends(get_db)):
    """All saved roles, newest first, with how many resumes and scores each
    has. Lets the UI reopen a role (and its saved ranking) after a refresh."""
    resume_counts = dict(
        db.query(JobResumeModel.job_id, func.count()).group_by(JobResumeModel.job_id).all()
    )
    score_counts = dict(
        db.query(ScoreModel.job_id, func.count()).group_by(ScoreModel.job_id).all()
    )
    jobs = db.query(JobModel).order_by(JobModel.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "title": j.title,
            "experience": j.experience,
            "created_at": j.created_at,
            "resume_count": resume_counts.get(j.id, 0),
            "scored_count": score_counts.get(j.id, 0),
            "scoring_status": j.scoring_status,
        }
        for j in jobs
    ]


@router.get("/{job_id}", response_model=JobDescriptionOut)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    record = db.get(JobModel, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


@router.get("/{job_id}/resumes")
async def list_job_resumes(job_id: str, db: Session = Depends(get_db)):
    """The resumes in this job's batch, with their processing status. Stuck
    resumes are flipped to 'failed' here, so a client polling this endpoint
    always reaches a final state."""
    if not db.get(JobModel, job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    expire_stale_parses(db, job_id=job_id)
    rows = (
        db.query(ResumeModel)
        .join(JobResumeModel, JobResumeModel.resume_id == ResumeModel.id)
        .filter(JobResumeModel.job_id == job_id)
        .order_by(JobResumeModel.added_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "status": r.status,
            "error": r.error,
            "warning": r.profile_warning,
            "status_changed_at": r.status_changed_at,
        }
        for r in rows
    ]



@router.delete("/{job_id}")
async def delete_job(job_id: str, only_if_empty: bool = False, db: Session = Depends(get_db)):
    """Deletes a role together with its scores (and therefore its shortlist /
    stage decisions) and its resume links.

    The resumes themselves and their files are NOT deleted: a resume is
    deduplicated by file hash and can belong to other roles too. A resume
    left with no roles simply stays in storage and is re-linked if it is
    uploaded again.

    only_if_empty=true is the safety catch for bulk clean-up: the role is
    deleted only if it has no resumes and no scores *right now*, otherwise
    409 — so a role that received an upload after the client last looked is
    never removed by mistake.
    """
    job = db.get(JobModel, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Role not found (it may already be deleted).")

    # A live scoring run would write scores for a role that no longer exists.
    if job.scoring_status in ("queued", "running"):
        beat = job.scoring_heartbeat_at
        if beat is not None and beat.tzinfo is None:
            beat = beat.replace(tzinfo=timezone.utc)
        if beat is not None and datetime.now(timezone.utc) - beat < timedelta(minutes=SCORING_STALE_MINUTES):
            raise HTTPException(
                status_code=409,
                detail="Scoring is running for this role. Wait for it to finish, then delete it.",
            )

    resume_links = db.query(JobResumeModel).filter(JobResumeModel.job_id == job_id).count()
    score_count = db.query(ScoreModel).filter(ScoreModel.job_id == job_id).count()
    if only_if_empty and (resume_links or score_count):
        raise HTTPException(status_code=409, detail="This role is no longer empty, so it was not deleted.")

    # Explicit deletes, children first, rather than relying on DB-level cascades.
    db.query(ScoreModel).filter(ScoreModel.job_id == job_id).delete(synchronize_session=False)
    db.query(JobResumeModel).filter(JobResumeModel.job_id == job_id).delete(synchronize_session=False)
    db.query(JobModel).filter(JobModel.id == job_id).delete(synchronize_session=False)
    db.commit()

    return {"deleted": job_id, "scores_removed": score_count, "resumes_unlinked": resume_links}
