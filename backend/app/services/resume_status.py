"""
Keeps resumes from sitting in "Processing…" forever.

A resume can get stuck in two ways:
  - "uploaded": it was queued but no worker ever picked it up (Celery not
    running, Redis restarted and lost the task, ...).
  - "parsing":  a worker started on it and then died or hung.

expire_stale_parses() is cheap and is called whenever the API reports resume
status, so a stuck resume flips to "failed" with a readable reason instead of
spinning. The user can then hit Retry.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import PARSE_TIMEOUT_MINUTES, QUEUE_TIMEOUT_MINUTES
from app.models.db_models import JobResumeModel, ResumeModel
from app.models.resume import ResumeStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def expire_stale_parses(db: Session, job_id: str | None = None) -> int:
    """Marks stuck resumes as failed. Limited to one job's batch when job_id
    is given. Returns how many were expired."""
    now = utcnow()
    q = db.query(ResumeModel).filter(
        ResumeModel.status.in_([ResumeStatus.uploaded.value, ResumeStatus.parsing.value])
    )
    if job_id is not None:
        q = q.join(JobResumeModel, JobResumeModel.resume_id == ResumeModel.id).filter(
            JobResumeModel.job_id == job_id
        )

    expired = 0
    for r in q.all():
        since = _aware(r.status_changed_at or r.uploaded_at)
        if r.status == ResumeStatus.uploaded.value:
            limit = timedelta(minutes=QUEUE_TIMEOUT_MINUTES)
            reason = (
                f"Not picked up for processing within {QUEUE_TIMEOUT_MINUTES} minutes. "
                "Is the Celery worker running? Use Retry once it is."
            )
        else:
            limit = timedelta(minutes=PARSE_TIMEOUT_MINUTES)
            reason = (
                f"Processing did not finish within {PARSE_TIMEOUT_MINUTES} minutes. "
                "The file may be corrupt or the worker may have crashed. Use Retry."
            )
        if now - since > limit:
            r.status = ResumeStatus.failed.value
            r.error = reason
            r.status_changed_at = now
            expired += 1

    if expired:
        db.commit()
    return expired
