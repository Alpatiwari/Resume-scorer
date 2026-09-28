"""
SQLAlchemy ORM models — the real Postgres tables backing jobs, resumes,
and scores.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    experience: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    nice_to_have_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Progress for the most recent scoring run against this job, so the
    # frontend can poll instead of holding one long HTTP request open.
    # scoring_status: idle | queued | running | done | failed
    scoring_status: Mapped[str] = mapped_column(String, default="idle")
    scoring_total: Mapped[int] = mapped_column(default=0)
    scoring_done: Mapped[int] = mapped_column(default=0)
    scoring_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bumped whenever the scoring run makes progress. Lets us tell a run that
    # is genuinely working from one whose worker died mid-way.
    scoring_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scores: Mapped[list["ScoreModel"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ResumeModel(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When `status` last changed. The stuck-parse check measures from here.
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Resume profile (skills/experience/education/projects/red_flags),
    # extracted once at parse time (in the Celery worker) instead of
    # being re-extracted via a fresh Gemini call every time this resume
    # is scored against a job — that extraction doesn't depend on the
    # job description, so redoing it per score run was pure waste.
    profile_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_education: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile_projects: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile_red_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Set when AI profile extraction failed and only keyword matching was used.
    profile_warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    scores: Mapped[list["ScoreModel"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class JobResumeModel(Base):
    """Which resumes belong to which job's batch. Scoring a job only looks at
    resumes linked here, so one role's uploads never leak into another's
    ranking. A resume (deduplicated by file hash) can be linked to many jobs."""
    __tablename__ = "job_resumes"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ScoreModel(Base):
    __tablename__ = "scores"
    # One score row per (job, resume). Re-scoring updates it in place, which is
    # what lets shortlist/stage decisions survive a re-score.
    __table_args__ = (UniqueConstraint("job_id", "resume_id", name="uq_scores_job_resume"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)

    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    # NULL means "this method could not run for this candidate" — never a
    # stand-in number. See services/scorer.py.
    skill_overlap_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Notes on anything that degraded this score (AI unavailable, etc).
    score_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    red_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")

    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Hiring pipeline stage: new | shortlisted | interview | offer | rejected
    stage: Mapped[str] = mapped_column(String, default="new", server_default="new", nullable=False)

    job: Mapped["JobModel"] = relationship(back_populates="scores")
    resume: Mapped["ResumeModel"] = relationship(back_populates="scores")