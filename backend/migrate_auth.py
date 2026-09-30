"""
One-off migration for the login system.

  python migrate_auth.py                                # apply the schema changes
  python migrate_auth.py --assign-existing-to EMAIL     # ...and hand every existing
                                                        # role + resume to that account

Safe to run more than once. Run it from backend/ with the venv active, and
BEFORE starting the API on the new code (the API can't read jobs/resumes until
the owner_id columns exist).

Typical first-time order:
  1. python migrate_auth.py
  2. python create_user.py you@example.com          (or register in the UI)
  3. python migrate_auth.py --assign-existing-to you@example.com

What it does:
  1. Creates the users table.
  2. Adds jobs.owner_id and resumes.owner_id (nullable, indexed, FK to users).
  3. With --assign-existing-to: gives every role and resume that has no owner
     to that user, so the data you already have stays visible after login.
     Roles/resumes with no owner are invisible to everyone until assigned.
"""
import sys

from sqlalchemy import text

from app.database import engine, init_db


def main() -> None:
    assign_to = None
    if "--assign-existing-to" in sys.argv:
        idx = sys.argv.index("--assign-existing-to")
        if idx + 1 >= len(sys.argv):
            raise SystemExit("--assign-existing-to needs an email address.")
        assign_to = sys.argv[idx + 1].strip().lower()

    init_db()  # creates the users table (and any other missing table)

    with engine.begin() as conn:
        for table in ("jobs", "resumes"):
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS owner_id VARCHAR "
                f"REFERENCES users(id) ON DELETE CASCADE"
            ))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON {table} (owner_id)"))

        jobs_assigned = resumes_assigned = 0
        if assign_to:
            row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": assign_to}).first()
            if not row:
                raise SystemExit(
                    f"No user with email {assign_to!r}. Create it first:\n"
                    f"  python create_user.py {assign_to}"
                )
            uid = row[0]
            jobs_assigned = conn.execute(
                text("UPDATE jobs SET owner_id = :u WHERE owner_id IS NULL"), {"u": uid}
            ).rowcount
            resumes_assigned = conn.execute(
                text("UPDATE resumes SET owner_id = :u WHERE owner_id IS NULL"), {"u": uid}
            ).rowcount

        orphan_jobs = conn.execute(text("SELECT count(*) FROM jobs WHERE owner_id IS NULL")).scalar()
        orphan_resumes = conn.execute(text("SELECT count(*) FROM resumes WHERE owner_id IS NULL")).scalar()

    print("Migration complete.")
    if assign_to:
        print(f"  roles assigned to {assign_to}   : {jobs_assigned}")
        print(f"  resumes assigned to {assign_to} : {resumes_assigned}")
    print(f"  roles still without an owner   : {orphan_jobs}")
    print(f"  resumes still without an owner : {orphan_resumes}")
    if (orphan_jobs or orphan_resumes) and not assign_to:
        print("  -> run again with --assign-existing-to EMAIL to keep that data visible.")


if __name__ == "__main__":
    main()

