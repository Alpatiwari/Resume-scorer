import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ALLOW_REGISTRATION
from app.database import get_db
from app.dependencies import get_current_user
from app.models.db_models import UserModel
from app.services.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    login_throttle,
    validate_password_strength,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None = None

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut


def _token_response(user: UserModel) -> TokenOut:
    token, expires_in = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{email}"


@router.get("/config")
async def auth_config():
    """Public. Lets the login page know whether to offer 'Create account'."""
    return {"registration_enabled": ALLOW_REGISTRATION}


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Sign-ups are disabled. Ask an administrator for an account.")

    email = normalize_email(body.email)
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    problem = validate_password_strength(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    if db.query(UserModel).filter(UserModel.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = UserModel(
        id=str(uuid.uuid4()),
        email=email,
        full_name=(body.full_name or "").strip() or None,
        password_hash=hash_password(body.password),
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two sign-ups with the same email raced past the check above
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    return _token_response(user)


# Sync `def` (not async): password hashing is deliberately slow CPU work, and
# FastAPI runs sync endpoints in a threadpool so it doesn't block other requests.
@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password form: `username` is the account's email."""
    email = normalize_email(form.username)
    key = _throttle_key(request, email)

    wait = login_throttle.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(UserModel).filter(UserModel.email == email).first()
    if user is None:
        burn_password_check(form.password)  # same timing as a wrong password
        ok = False
    else:
        ok = verify_password(form.password, user.password_hash) and user.is_active

    if not ok:
        login_throttle.record_failure(key)
        # One message for "no such email", "wrong password" and "disabled".
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_throttle.reset(key)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: UserModel = Depends(get_current_user)):
    return user
