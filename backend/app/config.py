from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE_MB = 10



GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("RESUME_SCORER_GEMINI_MODEL", "gemini-3.6-flash")

GEMINI_TIMEOUT_MS = int(os.environ.get("RESUME_SCORER_GEMINI_TIMEOUT_MS", "20000"))

SCORING_CONCURRENCY = int(os.environ.get("RESUME_SCORER_SCORING_CONCURRENCY", "5"))


# If Gemini fails for EVERY resume in a run, fail the run instead of saving
# scores that silently lack the LLM leg. Set to "true" to save them anyway
# (each row is still flagged with a warning) — e.g. to run keyword-only.
ALLOW_DEGRADED_SCORING = os.environ.get("RESUME_SCORER_ALLOW_DEGRADED_SCORING", "false").lower() == "true"

EMBEDDING_MODEL = os.environ.get("RESUME_SCORER_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


SCORE_WEIGHTS = {
    "skill_overlap": 0.30,
    "embedding": 0.25,
    "llm": 0.45,
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
