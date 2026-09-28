from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import jobs, resumes, scoring

app = FastAPI(title="Resume Filter & Scorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(scoring.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/llm")
def health_llm():
    """Makes one tiny real Gemini call with the configured key and model.
    Open this in a browser after changing GEMINI_MODEL / GEMINI_API_KEY: a wrong
    model name shows up here immediately instead of as degraded scores later."""
    from app.config import GEMINI_MODEL
    from app.services.gemini_client import GeminiUnavailableError, chat_json

    try:
        chat_json('Return exactly this JSON and nothing else: {"ok": true}')
    except GeminiUnavailableError as e:
        return {"ok": False, "model": GEMINI_MODEL, "error": str(e)}
    return {"ok": True, "model": GEMINI_MODEL, "error": None}
