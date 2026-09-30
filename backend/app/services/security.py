"""
Password hashing, JWT creation/validation and login throttling.

Deliberately free of FastAPI/SQLAlchemy imports so it can be unit-tested on
its own. Password hashing uses scrypt from the standard library (no extra
dependency, memory-hard); tokens use PyJWT.
"""
import base64
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt

from app import config

# scrypt cost parameters (OWASP-recommended combination). They are stored inside
# every hash, so they can be raised later without invalidating existing passwords.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_MAXMEM = 128 * 1024 * 1024
_SALT_BYTES = 16
_KEY_BYTES = 32

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128  # bounds the work an attacker can force per request

InvalidTokenError = jwt.InvalidTokenError


# ---------------------------------------------------------------- passwords

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=_SCRYPT_MAXMEM
    )


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    key = _derive(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _KEY_BYTES)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    """True only if `password` matches `stored`. Never raises on malformed input."""
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
        actual = _derive(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash: str | None = None


def burn_password_check(password: str) -> None:
    """Spends the same time as a real check. Called when the email is unknown,
    so response time doesn't reveal which emails have accounts."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    verify_password(password, _dummy_hash)


def validate_password_strength(password: str) -> str | None:
    """Returns an error message, or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    if password.strip() == "":
        return "Password can't be only spaces."
    return None


# ------------------------------------------------------------------- tokens

def _secret() -> str:
    key = config.JWT_SECRET_KEY
    if not key or len(key) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing or shorter than 32 characters. Add it to backend/.env:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
            "  JWT_SECRET_KEY=<the output>"
        )
    return key


def assert_auth_configured() -> None:
    """Called at API startup so a missing secret fails at boot, not on first login."""
    _secret()


def create_access_token(user_id: str, now: datetime | None = None) -> tuple[str, int]:
    """Returns (token, lifetime_in_seconds)."""
    now = now or datetime.now(timezone.utc)
    lifetime = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "iat": now, "exp": now + lifetime}
    token = jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> str:
    """Returns the user id inside a valid token; raises InvalidTokenError otherwise
    (bad signature, expired, malformed, wrong algorithm, missing claims)."""
    payload = jwt.decode(
        token,
        _secret(),
        algorithms=[config.JWT_ALGORITHM],  # pinned: rejects alg=none and algorithm-swap tricks
        options={"require": ["exp", "iat", "sub"]},
    )
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidTokenError("Token has no subject.")
    return sub


# ---------------------------------------------------------- login throttling

class LoginThrottle:
    """Sliding-window limit on FAILED logins per key (client IP + email).

    In-process memory only: fine for one uvicorn process. If you ever run
    several workers/servers, move this to Redis (you already have it)."""

    def __init__(self, max_failures: int, window_seconds: int, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._failures[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if not q:
            self._failures.pop(key, None)
            return deque()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds the caller must wait, or 0 if another attempt is allowed."""
        with self._lock:
            now = self._clock()
            q = self._prune(key, now)
            if len(q) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - q[0])) + 1)

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_throttle = LoginThrottle(config.LOGIN_MAX_FAILURES, config.LOGIN_FAILURE_WINDOW_SECONDS)
