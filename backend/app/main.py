from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from app.config import CORS_ORIGINS
from app.database import init_db
from app.dependencies import get_current_user
from app.routers import auth, jobs, resumes, scoring
from app.services.security import assert_auth_configured

app = FastAPI(title="Resume Filter & Scorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],  # includes Authorization
    expose_headers=["Content-Disposition"],  # lets the UI read export filenames
)

app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(scoring.router)


@app.on_event("startup")
def on_startup() -> None:
    assert_auth_configured()  # refuse to boot without a proper JWT_SECRET_KEY
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/llm", dependencies=[Depends(get_current_user)])
def health_llm():
    """Makes one tiny real Gemini call with the configured key and model.
    Requires a login now, so call it from /docs (use the Authorize button) after
    changing GEMINI_MODEL / GEMINI_API_KEY: a wrong model name shows up here
    immediately instead of as degraded scores later."""
    from app.config import GEMINI_MODEL
    from app.services.gemini_client import GeminiUnavailableError, chat_json

    try:
        chat_json('Return exactly this JSON and nothing else: {"ok": true}')
    except GeminiUnavailableError as e:
        return {"ok": False, "model": GEMINI_MODEL, "error": str(e)}
    return {"ok": True, "model": GEMINI_MODEL, "error": None}
