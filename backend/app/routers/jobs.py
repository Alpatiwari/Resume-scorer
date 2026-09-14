import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import JobModel
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
    return record


@router.get("/{job_id}", response_model=JobDescriptionOut)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    record = db.get(JobModel, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record