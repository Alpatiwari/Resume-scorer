"""
Real Postgres connection via SQLAlchemy, replacing the earlier in-memory
dict placeholder. DATABASE_URL comes from the environment (.env), e.g.:

    DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/resume_scorer
"""
import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to backend/.env, e.g.:\n"
        "DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/resume_scorer"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import db_models  # noqa: F401
    Base.metadata.create_all(bind=engine)