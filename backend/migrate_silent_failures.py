"""
One-off migration for the silent-failure fixes.

  python migrate_silent_failures.py

Safe to run more than once. Run from backend/ with the venv active, BEFORE
starting the API or Celery worker on the new code.

  1. scores.skill_overlap_score / embedding_score / llm_score become nullable
     (NULL = "that method could not run", instead of a fake 50 or 0).
  2. Adds scores.score_warnings and resumes.profile_warning.
  3. Finds existing scores that were saved with the old neutral-50
     placeholder ("LLM scoring skipped ...") and marks them: llm_score -> NULL
     plus a warning. Their final_score was computed WITH the fake 50, so
     re-score those roles to get correct numbers.
"""
import json

from sqlalchemy import text

from app.database import engine, init_db

LLM_WARNING = (
    "AI judgment was unavailable when this was scored (old run used a placeholder 50). "
    "Re-score this role to get a real score."
)


def main() -> None:
    init_db()
    with engine.begin() as conn:
        for col in ("skill_overlap_score", "embedding_score", "llm_score"):
            conn.execute(text(f"ALTER TABLE scores ALTER COLUMN {col} DROP NOT NULL"))
        conn.execute(text("ALTER TABLE scores ADD COLUMN IF NOT EXISTS score_warnings JSON"))
        conn.execute(text("UPDATE scores SET score_warnings = '[]'::json WHERE score_warnings IS NULL"))
        conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS profile_warning TEXT"))

        flagged = conn.execute(
            text(
                "UPDATE scores SET llm_score = NULL, score_warnings = CAST(:w AS json) "
                "WHERE reasoning LIKE 'LLM scoring skipped%'"
            ),
            {"w": json.dumps([LLM_WARNING])},
        ).rowcount

        jobs = conn.execute(
            text(
                "SELECT DISTINCT j.title FROM scores s JOIN jobs j ON j.id = s.job_id "
                "WHERE s.reasoning LIKE 'LLM scoring skipped%'"
            )
        ).fetchall()

    print("Migration complete.")
    print(f"  old placeholder-50 scores flagged: {flagged}")
    if jobs:
        print("  Re-score these roles:", ", ".join(sorted({r[0] for r in jobs})))


if __name__ == "__main__":
    main()