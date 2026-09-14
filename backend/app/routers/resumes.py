import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, STORAGE_DIR
from app.database import get_db
from app.models.db_models import ResumeModel
from app.models.resume import ResumeStatus, ResumeUploadResponse
from app.workers.celery_worker import process_resume

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.post("/upload", response_model=list[ResumeUploadResponse])
async def upload_resumes(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
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

        # Same bytes = same resume, even if the file was renamed. Return the
        # existing record instead of creating (and scoring) a second copy.
        content_hash = hashlib.sha256(contents).hexdigest()
        existing = db.query(ResumeModel).filter(ResumeModel.content_hash == content_hash).first()
        if existing:
            results.append(ResumeUploadResponse(
                id=existing.id, filename=upload.filename, status=ResumeStatus(existing.status),
                message=f"Already uploaded as '{existing.filename}' — using the existing copy.",
            ))
            continue

        resume_id = str(uuid.uuid4())
        saved_path = STORAGE_DIR / f"{resume_id}{suffix}"
        saved_path.write_bytes(contents)

        record = ResumeModel(
            id=resume_id, filename=upload.filename, status=ResumeStatus.uploaded.value,
            uploaded_at=datetime.now(timezone.utc), content_hash=content_hash,
        )
        db.add(record)
        db.commit()

        process_resume.delay(resume_id, str(saved_path))

        results.append(ResumeUploadResponse(
            id=resume_id, filename=upload.filename, status=ResumeStatus.uploaded,
            message="Queued for processing.",
        ))

    return results


@router.get("")
async def list_resumes(db: Session = Depends(get_db)):
    return db.query(ResumeModel).all()


@router.get("/{resume_id}")
async def get_resume(resume_id: str, db: Session = Depends(get_db)):
    record = db.get(ResumeModel, resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return record


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{resume_id}/file")
async def get_resume_file(resume_id: str, db: Session = Depends(get_db)):
    """Serves the original uploaded file so the UI can preview it. The
    resume must exist in the DB first, and the path is built from the
    DB-verified id + a whitelisted extension — never from user input —
    so this can't be used to read arbitrary files."""
    record = db.get(ResumeModel, resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found.")

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