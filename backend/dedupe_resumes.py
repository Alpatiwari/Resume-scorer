"""
One-off cleanup for resumes that were uploaded more than once before
duplicate detection existed.

  python dedupe_resumes.py            # dry run: only shows what WOULD happen
  python dedupe_resumes.py --apply    # actually does it

For every group of identical files (same bytes) it keeps the OLDEST upload
and deletes the other copies: their DB rows, their scores, and their files
in storage/. It also fills in content_hash for every resume so future
uploads are checked against them.

Run from the backend/ folder with the venv active.
"""
import hashlib
import sys
from collections import defaultdict

from app.config import STORAGE_DIR
from app.database import SessionLocal, init_db
from app.models.db_models import ResumeModel

APPLY = "--apply" in sys.argv


def find_file(resume_id: str):
    for ext in (".pdf", ".docx"):
        p = STORAGE_DIR / f"{resume_id}{ext}"
        if p.is_file():
            return p
    return None


def main() -> None:
    init_db()
    db = SessionLocal()
    resumes = db.query(ResumeModel).order_by(ResumeModel.uploaded_at.asc()).all()

    groups: dict[str, list[tuple[ResumeModel, object]]] = defaultdict(list)
    missing = []
    for r in resumes:
        f = find_file(r.id)
        if f is None:
            missing.append(r)
            continue
        groups[hashlib.sha256(f.read_bytes()).hexdigest()].append((r, f))
        if r.content_hash is None:
            r.content_hash = hashlib.sha256(f.read_bytes()).hexdigest()

    removed = 0
    for digest, members in groups.items():
        keeper, _ = members[0]
        dupes = members[1:]
        if not dupes:
            continue
        print(f"\nKeeping   {keeper.filename}  ({keeper.id[:8]})")
        for r, f in dupes:
            kept_decisions = [s for s in r.scores if s.shortlisted or s.stage != "new"]
            note = "  <- had a shortlist/stage decision that will be lost" if kept_decisions else ""
            print(f"  removing {r.filename}  ({r.id[:8]}), {len(r.scores)} score(s){note}")
            removed += 1
            if APPLY:
                db.delete(r)  # cascades to its scores
                f.unlink(missing_ok=True)

    if missing:
        print(f"\n{len(missing)} resume(s) have no file in storage and were left alone:")
        for r in missing:
            print(f"  {r.filename} ({r.id[:8]})")

    if APPLY:
        db.commit()
        print(f"\nDone. Removed {removed} duplicate resume(s); content_hash filled in.")
    else:
        db.rollback()
        print(f"\nDRY RUN: {removed} duplicate(s) would be removed. Nothing was changed.")
        print("Run again with --apply to do it.")
    db.close()


if __name__ == "__main__":
    main()