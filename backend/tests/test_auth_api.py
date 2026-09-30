"""
End-to-end tests for login and per-recruiter data isolation, using FastAPI's
TestClient against an in-memory SQLite database. No Postgres, Redis, Celery
worker or Gemini needed (queueing and AI extraction are mocked).

    pip install httpx pytest      # TestClient needs httpx
    pytest tests/test_auth_api.py -v
"""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"
os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.db_models import ScoreModel, UserModel
from app.routers import auth as auth_router
from app.routers import jobs as jobs_router
from app.routers import resumes as resumes_router
from app.services.security import login_throttle

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

PDF = b"%PDF-1.4 fake resume bytes"
PASSWORD = "correct-horse-battery"


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app.dependency_overrides[get_db] = _override_get_db
        login_throttle._failures.clear()
        self.client = TestClient(app)

        self.storage = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.object(resumes_router, "STORAGE_DIR", Path(self.storage.name)),
            mock.patch.object(resumes_router.process_resume, "delay"),
            mock.patch.object(
                jobs_router, "extract_job_requirements",
                return_value=SimpleNamespace(
                    required_skills=["Python"], nice_to_have_skills=[], min_experience_years=None, llm_error=None,
                ),
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.storage.cleanup)
        self.addCleanup(app.dependency_overrides.clear)

    # -- helpers
    def register(self, email, password=PASSWORD, name=None):
        return self.client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})

    def login(self, email, password=PASSWORD):
        return self.client.post("/api/auth/login", data={"username": email, "password": password})

    def headers_for(self, email):
        r = self.register(email)
        self.assertEqual(r.status_code, 201, r.text)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def make_job(self, headers, title="Backend Engineer"):
        r = self.client.post("/api/jobs", json={"title": title, "description": "Python role"}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def upload(self, headers, job_id, content=PDF, name="cv.pdf"):
        r = self.client.post(
            "/api/resumes/upload", data={"job_id": job_id}, files=[("files", (name, content, "application/pdf"))],
            headers=headers,
        )
        return r


class RegisterAndLoginTests(ApiTestCase):
    def test_register_returns_token_and_normalised_email(self):
        r = self.register("  Alice@Example.COM ", name="Alice")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["user"]["email"], "alice@example.com")
        self.assertEqual(body["token_type"], "bearer")
        self.assertNotIn("password_hash", body["user"])

    def test_password_is_stored_hashed(self):
        self.register("alice@example.com")
        with TestingSession() as db:
            stored = db.query(UserModel).one().password_hash
        self.assertNotIn(PASSWORD, stored)
        self.assertTrue(stored.startswith("scrypt$"))

    def test_duplicate_email_conflicts_case_insensitively(self):
        self.assertEqual(self.register("alice@example.com").status_code, 201)
        self.assertEqual(self.register("ALICE@example.com").status_code, 409)

    def test_bad_email_and_weak_password_rejected(self):
        self.assertEqual(self.register("not-an-email").status_code, 422)
        self.assertEqual(self.register("a@example.com", password="short").status_code, 422)

    def test_login_then_me(self):
        self.register("alice@example.com", name="Alice")
        r = self.login("Alice@Example.com")
        self.assertEqual(r.status_code, 200)
        token = r.json()["access_token"]
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "alice@example.com")

    def test_wrong_password_and_unknown_email_look_identical(self):
        self.register("alice@example.com")
        wrong = self.login("alice@example.com", "not-the-password")
        unknown = self.login("nobody@example.com", PASSWORD)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_lockout_after_repeated_failures(self):
        self.register("alice@example.com")
        for _ in range(5):
            self.assertEqual(self.login("alice@example.com", "wrong-password").status_code, 401)
        blocked = self.login("alice@example.com", PASSWORD)  # even the right password is refused now
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_registration_can_be_disabled(self):
        with mock.patch.object(auth_router, "ALLOW_REGISTRATION", False):
            self.assertEqual(self.register("alice@example.com").status_code, 403)
            self.assertFalse(self.client.get("/api/auth/config").json()["registration_enabled"])

    def test_deactivated_user_is_locked_out_immediately(self):
        headers = self.headers_for("alice@example.com")
        with TestingSession() as db:
            user = db.query(UserModel).one()
            user.is_active = False
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        self.assertEqual(self.login("alice@example.com").status_code, 401)

    def test_token_for_deleted_user_is_rejected(self):
        headers = self.headers_for("alice@example.com")
        with TestingSession() as db:
            db.delete(db.query(UserModel).one())
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)


class ProtectionTests(ApiTestCase):
    def test_health_is_public_but_everything_else_needs_a_token(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        for method, url in [
            ("get", "/api/auth/me"),
            ("get", "/api/jobs"),
            ("post", "/api/jobs"),
            ("get", "/api/jobs/x"),
            ("delete", "/api/jobs/x"),
            ("get", "/api/jobs/x/resumes"),
            ("get", "/api/resumes"),
            ("get", "/api/resumes/x"),
            ("get", "/api/resumes/x/file"),
            ("post", "/api/resumes/x/retry"),
            ("post", "/api/resumes/upload"),
            ("post", "/api/score/x"),
            ("get", "/api/score/x"),
            ("get", "/api/score/x/status"),
            ("get", "/api/score/x/export"),
            ("get", "/api/score/x/export.pdf"),
            ("patch", "/api/score/item/1/shortlist"),
            ("patch", "/api/score/item/1/stage"),
            ("get", "/api/health/llm"),
        ]:
            r = getattr(self.client, method)(url)
            self.assertEqual(r.status_code, 401, f"{method.upper()} {url} -> {r.status_code}")

    def test_garbage_and_wrongly_signed_tokens_rejected(self):
        for token in ["garbage", "a.b.c"]:
            r = self.client.get("/api/jobs", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(r.status_code, 401)


class IsolationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.headers_for("alice@example.com")
        self.bob = self.headers_for("bob@example.com")
        self.alice_job = self.make_job(self.alice)

    def test_each_user_only_lists_their_own_roles(self):
        bob_job = self.make_job(self.bob, "Designer")
        self.assertEqual([j["id"] for j in self.client.get("/api/jobs", headers=self.alice).json()], [self.alice_job])
        self.assertEqual([j["id"] for j in self.client.get("/api/jobs", headers=self.bob).json()], [bob_job])

    def test_other_users_role_is_404_everywhere(self):
        j = self.alice_job
        for method, url in [
            ("get", f"/api/jobs/{j}"),
            ("delete", f"/api/jobs/{j}"),
            ("get", f"/api/jobs/{j}/resumes"),
            ("post", f"/api/score/{j}"),
            ("get", f"/api/score/{j}"),
            ("get", f"/api/score/{j}/status"),
            ("get", f"/api/score/{j}/export"),
            ("get", f"/api/score/{j}/export.pdf"),
        ]:
            r = getattr(self.client, method)(url, headers=self.bob)
            self.assertEqual(r.status_code, 404, f"{method.upper()} {url} -> {r.status_code}")
        # ...and nothing was deleted by Bob's attempt
        self.assertEqual(self.client.get(f"/api/jobs/{j}", headers=self.alice).status_code, 200)

    def test_cannot_upload_into_someone_elses_role(self):
        r = self.upload(self.bob, self.alice_job)
        self.assertEqual(r.status_code, 404)

    def test_resume_records_and_files_are_private(self):
        rid = self.upload(self.alice, self.alice_job).json()[0]["id"]
        self.assertEqual(self.client.get(f"/api/resumes/{rid}", headers=self.alice).status_code, 200)
        self.assertEqual(self.client.get(f"/api/resumes/{rid}/file", headers=self.alice).status_code, 200)

        for method, url in [("get", f"/api/resumes/{rid}"), ("get", f"/api/resumes/{rid}/file"),
                            ("post", f"/api/resumes/{rid}/retry")]:
            self.assertEqual(getattr(self.client, method)(url, headers=self.bob).status_code, 404, url)
        self.assertEqual(self.client.get("/api/resumes", headers=self.bob).json(), [])
        self.assertEqual([r["id"] for r in self.client.get("/api/resumes", headers=self.alice).json()], [rid])

    def test_identical_file_from_two_users_is_not_shared(self):
        alice_id = self.upload(self.alice, self.alice_job).json()[0]["id"]
        bob_job = self.make_job(self.bob, "Designer")
        bob_resp = self.upload(self.bob, bob_job).json()[0]
        self.assertNotEqual(bob_resp["id"], alice_id)
        self.assertNotIn("Already uploaded", bob_resp["message"])  # must not hint that Alice has it

    def test_duplicate_within_one_users_account_is_still_reused(self):
        first = self.upload(self.alice, self.alice_job).json()[0]["id"]
        second_job = self.make_job(self.alice, "Second role")
        again = self.upload(self.alice, second_job).json()[0]
        self.assertEqual(again["id"], first)
        self.assertIn("Already uploaded", again["message"])

    def test_shortlist_and_stage_on_someone_elses_score_is_404(self):
        rid = self.upload(self.alice, self.alice_job).json()[0]["id"]
        with TestingSession() as db:
            score = ScoreModel(job_id=self.alice_job, resume_id=rid, filename="cv.pdf", final_score=80.0)
            db.add(score)
            db.commit()
            sid = score.id

        for kind, body in (("shortlist", {"shortlisted": True}), ("stage", {"stage": "offer"})):
            url = f"/api/score/item/{sid}/{kind}"
            self.assertEqual(self.client.patch(url, json=body, headers=self.bob).status_code, 404)
            self.assertEqual(self.client.patch(url, json=body, headers=self.alice).status_code, 200)

    def test_legacy_role_without_owner_is_invisible(self):
        from app.models.db_models import JobModel
        with TestingSession() as db:
            db.add(JobModel(id="legacy-1", title="Old role", description="d", owner_id=None))
            db.commit()
        self.assertEqual(self.client.get("/api/jobs/legacy-1", headers=self.alice).status_code, 404)
        self.assertNotIn("legacy-1", [j["id"] for j in self.client.get("/api/jobs", headers=self.alice).json()])


if __name__ == "__main__":
    unittest.main()
