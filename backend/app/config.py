from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE_MB = 10



# Browser origins allowed to call the API (comma separated). Set this to your
# deployed frontend URL(s), e.g. RESUME_SCORER_CORS_ORIGINS=https://app.example.com
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("RESUME_SCORER_CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("RESUME_SCORER_GEMINI_MODEL", "gemini-3.6-flash")

GEMINI_TIMEOUT_MS = int(os.environ.get("RESUME_SCORER_GEMINI_TIMEOUT_MS", "20000"))

SCORING_CONCURRENCY = int(os.environ.get("RESUME_SCORER_SCORING_CONCURRENCY", "5"))


# If Gemini fails for EVERY resume in a run, fail the run instead of saving
# scores that silently lack the LLM leg. Set to "true" to save them anyway
# (each row is still flagged with a warning) — e.g. to run keyword-only.
ALLOW_DEGRADED_SCORING = os.environ.get("RESUME_SCORER_ALLOW_DEGRADED_SCORING", "false").lower() == "true"

EMBEDDING_MODEL = os.environ.get("RESUME_SCORER_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


# Must add up to 1.0. The embedding leg is weighted lowest: raw cosine
# similarity from a small model is on a different scale from the other legs
# and only "sees" the start of a long resume. "experience" only counts when
# the job states a minimum number of years and the resume's years are known.
SCORE_WEIGHTS = {
    "skill_overlap": 0.30,
    "embedding": 0.15,
    "llm": 0.45,
    "experience": 0.10,
}


# --- Resume parsing / scoring timeouts (point 2: no more stuck jobs) ---
# A resume waiting in the queue this long was never picked up (worker down?).
QUEUE_TIMEOUT_MINUTES = int(os.environ.get("RESUME_SCORER_QUEUE_TIMEOUT_MINUTES", "30"))
# A resume that a worker started on but never finished within this long is stuck.
PARSE_TIMEOUT_MINUTES = int(os.environ.get("RESUME_SCORER_PARSE_TIMEOUT_MINUTES", "5"))
# Celery kills a single parse task after this many seconds.
PARSE_SOFT_TIME_LIMIT_SECONDS = int(os.environ.get("RESUME_SCORER_PARSE_SOFT_LIMIT_SECONDS", "120"))
# A scoring run with no progress for this long is treated as dead and may be restarted.
SCORING_STALE_MINUTES = int(os.environ.get("RESUME_SCORER_SCORING_STALE_MINUTES", "15"))


# --- Authentication (JWT) ---
# No default on purpose: a guessable signing key would let anyone forge logins.
# Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("RESUME_SCORER_ACCESS_TOKEN_MINUTES", "480"))  # 8h = one workday

# Set to "false" once your recruiters have accounts (create more with create_user.py).
ALLOW_REGISTRATION = os.environ.get("RESUME_SCORER_ALLOW_REGISTRATION", "true").lower() == "true"

# Failed logins allowed per (client IP, email) inside the window before a temporary lockout.
LOGIN_MAX_FAILURES = int(os.environ.get("RESUME_SCORER_LOGIN_MAX_FAILURES", "5"))
LOGIN_FAILURE_WINDOW_SECONDS = int(os.environ.get("RESUME_SCORER_LOGIN_WINDOW_SECONDS", "900"))
