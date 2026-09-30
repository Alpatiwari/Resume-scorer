"""
Shared FastAPI dependencies: who is calling, and what they're allowed to touch.

Anything a user doesn't own answers 404 (not 403), so the API never confirms
that someone else's role/resume/score exists.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import JobModel, ResumeModel, ScoreModel, UserModel
from app.services.security import InvalidTokenError, decode_access_token

# tokenUrl makes the "Authorize" button in /docs work (it posts email as `username`).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in, or your session expired. Please sign in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise _UNAUTHORIZED
    user = db.get(UserModel, user_id)
    # Re-checked on every request, so deactivating/deleting a user cuts them off
    # immediately instead of when their token expires.
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def get_owned_job(db: Session, job_id: str, user: UserModel) -> JobModel:
    job = db.get(JobModel, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def get_owned_resume(db: Session, resume_id: str, user: UserModel) -> ResumeModel:
    resume = db.get(ResumeModel, resume_id)
    if resume is None or resume.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


def get_owned_score(db: Session, score_id: int, user: UserModel) -> ScoreModel:
    score = db.get(ScoreModel, score_id)
    job = db.get(JobModel, score.job_id) if score else None
    if score is None or job is None or job.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Score not found.")
    return score
