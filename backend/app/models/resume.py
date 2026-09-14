from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ResumeStatus(str, Enum):
    uploaded = "uploaded"
    parsed = "parsed"
    failed = "failed"


class ResumeRecord(BaseModel):
    id: str
    filename: str
    status: ResumeStatus
    uploaded_at: datetime
    extracted_text: str | None = None
    error: str | None = None

    class Config:
        use_enum_values = True


class ResumeUploadResponse(BaseModel):
    id: str
    filename: str
    status: ResumeStatus
    message: str
