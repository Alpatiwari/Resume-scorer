"""Runs before any test module is imported: gives the tests their own JWT key
and a throwaway SQLite database, so they never touch your real .env values."""
import os

os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"
os.environ.setdefault("DATABASE_URL", "sqlite://")
