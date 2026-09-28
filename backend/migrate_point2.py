"""
One-off migration for the batch-scoping / re-score / stuck-parse fixes.

  python migrate_point2.py                       # apply the migration
  python migrate_point2.py --link-all-to JOB_ID  # ...and also attach every existing
                                                 # resume to that job's batch

Safe to run more than once. Run it from backend/ with the venv active, and
BEFORE starting the API or the Celery worker on the new code.

What it does:
  1. Creates the new job_resumes table (which resumes belong to which job).
  2. Adds resumes.status_changed_at and jobs.scoring_heartbeat_at.
  3. Removes duplicate (job, resume) score rows (keeps the newest) and adds a
     unique index so re-scoring can update rows in place.
  4. Links every resume that already has a score to the job it was scored for,
     so existing rankings keep working.
"""
import sys

from sqlalchemy import text

from app.database import SessionLocal, engine, init_db


def main() -> None:
    link_all_to = None
    if "--link-all-to" in sys.argv:
        link_all_to = sys.argv[sys.argv.index("--link-all-to") + 1]

    init_db()  # creates job_resumes (and any other missing table)

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scoring_heartbeat_at TIMESTAMPTZ"))

        removed = conn.execute(text(
            "DELETE FROM scores a USING scores b "
            "WHERE a.job_id = b.job_id AND a.resume_id = b.resume_id AND a.id < b.id"
        )).rowcount
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scores_job_resume ON scores (job_id, resume_id)"
        ))

        linked = conn.execute(text(
            "INSERT INTO job_resumes (job_id, resume_id, added_at) "
            "SELECT DISTINCT job_id, resume_id, now() FROM scores "
            "ON CONFLICT DO NOTHING"
        )).rowcount

        extra = 0
        if link_all_to:
            found = conn.execute(text("SELECT 1 FROM jobs WHERE id = :j"), {"j": link_all_to}).first()
            if not found:
                raise SystemExit(f"No job with id {link_all_to!r}; nothing linked.")
            extra = conn.execute(text(
                "INSERT INTO job_resumes (job_id, resume_id, added_at) "
                "SELECT :j, id, now() FROM resumes ON CONFLICT DO NOTHING"
            ), {"j": link_all_to}).rowcount

        # A resume that was mid-parse under the old code has no timestamp yet.
        conn.execute(text(
            "UPDATE resumes SET status_changed_at = uploaded_at WHERE status_changed_at IS NULL"
        ))

    print("Migration complete.")
    print(f"  duplicate score rows removed : {removed}")
    print(f"  resumes linked from scores   : {linked}")
    if link_all_to:
        print(f"  resumes linked to {link_all_to[:8]}…  : {extra}")


if __name__ == "__main__":
    main()
