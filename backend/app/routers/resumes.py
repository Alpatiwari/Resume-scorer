import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, STORAGE_DIR
from app.database import get_db
from app.dependencies import get_current_user, get_owned_job, get_owned_resume
from app.models.db_models import JobModel, JobResumeModel, ResumeModel, ScoreModel, UserModel
from app.models.resume import ResumeStatus, ResumeUploadResponse
from app.routers.jobs import _scoring_is_live
from app.services.resume_status import utcnow
from app.workers.celery_worker import process_resume

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resumes", tags=["resumes"], dependencies=[Depends(get_current_user)])


def find_stored_file(resume_id: str):
    for suffix in _MEDIA_TYPES:
        path = STORAGE_DIR / f"{resume_id}{suffix}"
        if path.is_file():
            return path
    return None


def _link_to_job(db: Session, job_id: str, resume_id: str) -> None:
    if db.get(JobResumeModel, (job_id, resume_id)) is None:
        db.add(JobResumeModel(job_id=job_id, resume_id=resume_id))


def _requeue(db: Session, record: ResumeModel, path) -> None:
    record.status = ResumeStatus.uploaded.value
    record.error = None
    record.status_changed_at = utcnow()
    db.commit()
    process_resume.delay(record.id, str(path))


@router.post("/upload", response_model=list[ResumeUploadResponse])
async def upload_resumes(
    job_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Uploads resumes into ONE job's batch. Only resumes linked to a job
    are scored for it."""
    try:
        get_owned_job(db, job_id, user)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Job not found. Save the role before uploading.")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results: list[ResumeUploadResponse] = []

    for upload in files:
        suffix = "." + upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""

        if suffix not in ALLOWED_EXTENSIONS:
            results.append(ResumeUploadResponse(
                id="", filename=upload.filename, status=ResumeStatus.failed,
                message=f"Unsupported file type '{suffix}'. Only PDF and DOCX are accepted.",
            ))
            continue

        contents = await upload.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            results.append(ResumeUploadResponse(
                id="", filename=upload.filename, status=ResumeStatus.failed,
                message=f"File exceeds {MAX_FILE_SIZE_MB}MB limit.",
            ))
            continue

        # Same bytes = same resume, even if the file was renamed. Reuse the
        # existing record (no second copy, no second parse) but still add it
        # to THIS job's batch so it gets scored for this role.
        content_hash = hashlib.sha256(contents).hexdigest()
        # Matched per owner: another recruiter's identical file is a separate record.
        existing = (
            db.query(ResumeModel)
            .filter(ResumeModel.content_hash == content_hash, ResumeModel.owner_id == user.id)
            .first()
        )
        if existing:
            _link_to_job(db, job_id, existing.id)
            message = f"Already uploaded as '{existing.filename}' — reusing it for this role."
            stored = find_stored_file(existing.id)
            if existing.status == ResumeStatus.failed.value and stored:
                _requeue(db, existing, stored)  # commits
                message = f"Earlier attempt failed, so '{existing.filename}' was queued again."
            else:
                db.commit()
            results.append(ResumeUploadResponse(
                id=existing.id, filename=upload.filename, status=ResumeStatus(existing.status),
                message=message,
            ))
            continue

        resume_id = str(uuid.uuid4())
        saved_path = STORAGE_DIR / f"{resume_id}{suffix}"
        saved_path.write_bytes(contents)

        now = utcnow()
        record = ResumeModel(
            id=resume_id, owner_id=user.id, filename=upload.filename, status=ResumeStatus.uploaded.value,
            uploaded_at=now, status_changed_at=now, content_hash=content_hash,
        )
        db.add(record)
        db.flush()  # the resume row must exist before the link row that references it
        _link_to_job(db, job_id, resume_id)
        db.commit()

        process_resume.delay(resume_id, str(saved_path))

        results.append(ResumeUploadResponse(
            id=resume_id, filename=upload.filename, status=ResumeStatus.uploaded,
            message="Queued for processing.",
        ))

    return results


@router.post("/{resume_id}/retry")
async def retry_resume(resume_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Re-queues a resume whose processing failed or timed out."""
    record = get_owned_resume(db, resume_id, user)
    if record.status != ResumeStatus.failed.value:
        raise HTTPException(status_code=409, detail=f"Only failed resumes can be retried (this one is '{record.status}').")
    stored = find_stored_file(record.id)
    if not stored:
        raise HTTPException(status_code=404, detail="The original file is no longer in storage. Please upload it again.")
    _requeue(db, record, stored)
    return {"id": record.id, "status": record.status}


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Permanently deletes a resume: its text and profile, its scores (and the
    shortlist/stage/notes on them), its links to every role, and the stored
    file. Because identical files are shared across a recruiter's roles, it
    disappears from ALL of them. Refused while a role it belongs to is being
    scored, so a running job never writes a score for a resume that is gone."""
    record = get_owned_resume(db, resume_id, user)
    rid = record.id  # read now: after the delete + commit the object can no longer be touched

    linked_jobs = (
        db.query(JobModel)
        .join(JobResumeModel, JobResumeModel.job_id == JobModel.id)
        .filter(JobResumeModel.resume_id == rid)
        .all()
    )
    if any(_scoring_is_live(j) for j in linked_jobs):
        raise HTTPException(
            status_code=409,
            detail="Scoring is running for a role this resume belongs to. Wait for it to finish, then delete it.",
        )

    # Explicit deletes, children first (same approach as deleting a role).
    scores_removed = db.query(ScoreModel).filter(ScoreModel.resume_id == rid).delete(synchronize_session=False)
    links_removed = db.query(JobResumeModel).filter(JobResumeModel.resume_id == rid).delete(synchronize_session=False)
    db.query(ResumeModel).filter(ResumeModel.id == rid).delete(synchronize_session=False)
    db.commit()

    # Files go only after the DB commit succeeded. A leftover file with no DB row is
    # harmless and unreachable; a DB row pointing at a missing file would not be.
    for suffix in _MEDIA_TYPES:
        try:
            (STORAGE_DIR / f"{rid}{suffix}").unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not delete stored file for resume %s", rid)

    return {"deleted": resume_id, "scores_removed": scores_removed, "roles_unlinked": links_removed}


@router.get("")
async def list_resumes(db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    return db.query(ResumeModel).filter(ResumeModel.owner_id == user.id).all()


@router.get("/{resume_id}")
async def get_resume(resume_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    return get_owned_resume(db, resume_id, user)


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{resume_id}/file")
async def get_resume_file(resume_id: str, db: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    """Serves the original uploaded file so the UI can preview it. The
    resume must exist in the DB first, and the path is built from the
    DB-verified id + a whitelisted extension — never from user input —
    so this can't be used to read arbitrary files."""
    record = get_owned_resume(db, resume_id, user)

    for suffix, media_type in _MEDIA_TYPES.items():
        path = STORAGE_DIR / f"{record.id}{suffix}"
        if path.is_file():
            return FileResponse(
                path,
                media_type=media_type,
                filename=record.filename,
                content_disposition_type="inline",
            )
    raise HTTPException(status_code=404, detail="Original file is no longer in storage.")