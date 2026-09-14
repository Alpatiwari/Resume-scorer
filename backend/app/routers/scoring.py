import csv
import io
from datetime import datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import JobModel, ResumeModel, ScoreModel
from app.workers.celery_worker import score_job

router = APIRouter(prefix="/api/score", tags=["scoring"])

# Hiring pipeline. "shortlisted" (the boolean) stays in sync with this so the
# existing checkbox / filter / CSV keep working: anything past "new" that
# isn't "rejected" counts as shortlisted.
STAGES = ["new", "shortlisted", "interview", "offer", "rejected"]
_SHORTLISTED_STAGES = {"shortlisted", "interview", "offer"}


def _serialize(score: ScoreModel, resume: ResumeModel | None) -> dict:
    """Score row + the candidate's profile highlights (experience, education,
    projects) so the breakdown can show *why* they fit, not only numbers."""
    return {
        "id": score.id,
        "job_id": score.job_id,
        "resume_id": score.resume_id,
        "filename": score.filename,
        "final_score": score.final_score,
        "skill_overlap_score": score.skill_overlap_score,
        "embedding_score": score.embedding_score,
        "llm_score": score.llm_score,
        "matched_skills": score.matched_skills or [],
        "missing_skills": score.missing_skills or [],
        "red_flags": score.red_flags or [],
        "reasoning": score.reasoning,
        "scored_at": score.scored_at,
        "shortlisted": score.shortlisted,
        "stage": score.stage,
        "experience_years": resume.profile_experience_years if resume else None,
        "education": (resume.profile_education if resume else None) or [],
        "projects": (resume.profile_projects if resume else None) or [],
    }


@router.post("/{job_id}")
async def start_scoring(job_id: str, db: Session = Depends(get_db)):
    """Queues scoring as a background Celery task and returns immediately
    — it does NOT wait for scoring to finish. Poll GET /{job_id}/status
    for progress, then GET /{job_id} once status is "done"."""
    job = db.get(JobModel, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    has_parsed = db.query(ResumeModel).filter(ResumeModel.status == "parsed").first()
    if not has_parsed:
        raise HTTPException(status_code=400, detail="No parsed resumes to score yet. Upload some first.")

    job.scoring_status = "queued"
    job.scoring_error = None
    db.commit()

    score_job.delay(job_id)

    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}/status")
async def get_scoring_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(JobModel, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {
        "status": job.scoring_status,
        "done": job.scoring_done,
        "total": job.scoring_total,
        "error": job.scoring_error,
    }


class ShortlistIn(BaseModel):
    shortlisted: bool


@router.patch("/item/{score_id}/shortlist")
async def set_shortlist(score_id: int, body: ShortlistIn, db: Session = Depends(get_db)):
    score = db.get(ScoreModel, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found.")
    score.shortlisted = body.shortlisted
    if body.shortlisted and score.stage not in _SHORTLISTED_STAGES:
        score.stage = "shortlisted"
    elif not body.shortlisted and score.stage in _SHORTLISTED_STAGES:
        score.stage = "new"
    db.commit()
    return {"id": score.id, "shortlisted": score.shortlisted, "stage": score.stage}


class StageIn(BaseModel):
    stage: str


@router.patch("/item/{score_id}/stage")
async def set_stage(score_id: int, body: StageIn, db: Session = Depends(get_db)):
    """Moves a candidate to another hiring stage."""
    if body.stage not in STAGES:
        raise HTTPException(status_code=422, detail=f"Stage must be one of: {', '.join(STAGES)}.")
    score = db.get(ScoreModel, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found.")
    score.stage = body.stage
    score.shortlisted = body.stage in _SHORTLISTED_STAGES
    db.commit()
    return {"id": score.id, "stage": score.stage, "shortlisted": score.shortlisted}


def _export_rows(db: Session, job_id: str, shortlisted_only: bool, min_score: float, stage: str | None):
    q = db.query(ScoreModel).filter(
        ScoreModel.job_id == job_id, ScoreModel.final_score >= min_score
    )
    if shortlisted_only:
        q = q.filter(ScoreModel.shortlisted.is_(True))
    if stage:
        q = q.filter(ScoreModel.stage == stage)
    rows = q.order_by(ScoreModel.final_score.desc()).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Nothing to export with these filters.")
    return rows


@router.get("/{job_id}/export")
async def export_scores(
    job_id: str,
    shortlisted_only: bool = False,
    min_score: float = 0,
    stage: str | None = None,
    db: Session = Depends(get_db),
):
    rows = _export_rows(db, job_id, shortlisted_only, min_score, stage)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Rank", "Candidate", "Final score", "Skill overlap", "Embedding", "LLM",
                "Matched skills", "Missing skills", "Red flags", "Reasoning", "Stage", "Shortlisted"])
    for i, r in enumerate(rows, start=1):
        w.writerow([i, r.filename, r.final_score, r.skill_overlap_score, r.embedding_score,
                    r.llm_score, ", ".join(r.matched_skills or []), ", ".join(r.missing_skills or []),
                    ", ".join(r.red_flags or []), r.reasoning, r.stage, "Yes" if r.shortlisted else "No"])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="shortlist-{job_id[:8]}.csv"'},
    )


@router.get("/{job_id}/export.pdf")
async def export_scores_pdf(
    job_id: str,
    shortlisted_only: bool = False,
    min_score: float = 0,
    stage: str | None = None,
    db: Session = Depends(get_db),
):
    """Same filters as the CSV export, rendered as a printable PDF report."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    job = db.get(JobModel, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    rows = _export_rows(db, job_id, shortlisted_only, min_score, stage)

    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell")
    cell.fontSize = 8
    cell.leading = 10

    def P(text: str) -> Paragraph:
        # Paragraph parses XML-ish markup, so user/LLM text must be escaped.
        return Paragraph(escape(text or "—"), cell)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), title=f"Shortlist - {job.title}",
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
    )

    filters = []
    if shortlisted_only:
        filters.append("shortlisted only")
    if min_score:
        filters.append(f"score \u2265 {min_score:g}")
    if stage:
        filters.append(f"stage: {stage}")

    story = [
        Paragraph(escape(f"Candidate shortlist \u2014 {job.title}"), styles["Title"]),
        Paragraph(
            escape(f"Generated {datetime.now():%d %b %Y, %H:%M} \u00b7 {len(rows)} candidate(s)"
                   + (f" \u00b7 {', '.join(filters)}" if filters else "")),
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
    ]

    data = [[P(h) for h in ("#", "Candidate", "Score", "Stage", "Matched skills", "Missing skills", "Red flags", "Summary")]]
    for i, r in enumerate(rows, start=1):
        data.append([
            P(str(i)), P(r.filename), P(f"{r.final_score:g}"), P(r.stage),
            P(", ".join(r.matched_skills or [])), P(", ".join(r.missing_skills or [])),
            P(", ".join(r.red_flags or [])), P(r.reasoning),
        ])

    table = Table(
        data, repeatRows=1,
        colWidths=[8 * mm, 42 * mm, 14 * mm, 20 * mm, 45 * mm, 40 * mm, 35 * mm, 58 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e2d0")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8b2a0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf8f2")]),
    ]))
    story.append(table)
    doc.build(story)

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="shortlist-{job_id[:8]}.pdf"'},
    )


@router.get("/{job_id}")
async def get_scores(job_id: str, db: Session = Depends(get_db)):
    pairs = (
        db.query(ScoreModel, ResumeModel)
        .outerjoin(ResumeModel, ResumeModel.id == ScoreModel.resume_id)
        .filter(ScoreModel.job_id == job_id)
        .order_by(ScoreModel.final_score.desc())
        .all()
    )
    if not pairs:
        raise HTTPException(status_code=404, detail="No scores yet for this job. POST to this URL first.")
    return [_serialize(score, resume) for score, resume in pairs]
