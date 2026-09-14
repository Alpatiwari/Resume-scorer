"""
Celery application instance — separate from FastAPI's app so both the
API process and the worker process can import it without pulling in
each other's routes.

Run the worker with:
    celery -A app.celery_app.celery_app worker --loglevel=info

Requires Redis running locally:
    redis-server
"""
import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "resume_scorer",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

celery_app.autodiscover_tasks(["app.workers"], related_name="celery_worker")