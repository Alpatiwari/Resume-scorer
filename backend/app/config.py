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


EMBEDDING_MODEL = os.environ.get("RESUME_SCORER_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


SCORE_WEIGHTS = {
    "skill_overlap": 0.30,
    "embedding": 0.25,
    "llm": 0.45,
}
