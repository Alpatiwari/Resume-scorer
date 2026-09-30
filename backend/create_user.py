"""
Create a recruiter account from the command line (works even when
RESUME_SCORER_ALLOW_REGISTRATION=false).

  python create_user.py you@example.com
  python create_user.py you@example.com --name "Asha Verma"

The password is prompted for (never passed on the command line, so it doesn't
end up in your shell history). Run from backend/ with the venv active.
"""
import getpass
import re
import sys
import uuid

from app.database import SessionLocal, init_db
from app.models.db_models import UserModel
from app.services.security import hash_password, validate_password_strength


def main() -> None:
    args = [a for a in sys.argv[1:]]
    name = None
    if "--name" in args:
        i = args.index("--name")
        name = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if len(args) != 1:
        raise SystemExit(__doc__)

    email = args[0].strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise SystemExit(f"{email!r} is not a valid email address.")

    init_db()
    db = SessionLocal()
    try:
        if db.query(UserModel).filter(UserModel.email == email).first():
            raise SystemExit(f"An account for {email} already exists.")

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords don't match.")
        problem = validate_password_strength(password)
        if problem:
            raise SystemExit(problem)

        db.add(UserModel(
            id=str(uuid.uuid4()), email=email,
            full_name=(name or "").strip() or None,
            password_hash=hash_password(password),
        ))
        db.commit()
        print(f"Created account for {email}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
