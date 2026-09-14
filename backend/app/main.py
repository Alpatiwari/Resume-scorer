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