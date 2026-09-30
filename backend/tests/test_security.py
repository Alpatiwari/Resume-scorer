"""
Tests for password hashing, JWTs and login throttling. Pure Python: no
database, Redis, Gemini or web framework needed.

    python -m unittest discover -s tests -t . -v      (or: pytest -v)
"""
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"

import jwt

from app import config
from app.services import security
from app.services.security import LoginThrottle


class PasswordTests(unittest.TestCase):
    def test_correct_password_verifies(self):
        h = security.hash_password("correct horse battery")
        self.assertTrue(security.verify_password("correct horse battery", h))

    def test_wrong_password_fails(self):
        h = security.hash_password("correct horse battery")
        self.assertFalse(security.verify_password("correct horse batterY", h))
        self.assertFalse(security.verify_password("", h))

    def test_same_password_hashes_differently_each_time(self):
        self.assertNotEqual(security.hash_password("samepassword1"), security.hash_password("samepassword1"))

    def test_hash_does_not_contain_the_password(self):
        self.assertNotIn("hunter22hunter", security.hash_password("hunter22hunter"))

    def test_unicode_password(self):
        h = security.hash_password("pässwörd-密码-🔑")
        self.assertTrue(security.verify_password("pässwörd-密码-🔑", h))

    def test_malformed_stored_hash_is_rejected_not_raised(self):
        for bad in ["", "garbage", "scrypt$1$2", "bcrypt$a$b$c$d$e", "scrypt$x$y$z$!!$!!"]:
            self.assertFalse(security.verify_password("anything", bad), bad)

    def test_strength_rules(self):
        self.assertIsNotNone(security.validate_password_strength("short"))
        self.assertIsNotNone(security.validate_password_strength("        "))
        self.assertIsNotNone(security.validate_password_strength("x" * 129))
        self.assertIsNone(security.validate_password_strength("long enough pw"))
        self.assertIsNone(security.validate_password_strength("x" * 128))


class TokenTests(unittest.TestCase):
    def test_round_trip(self):
        token, lifetime = security.create_access_token("user-123")
        self.assertEqual(security.decode_access_token(token), "user-123")
        self.assertEqual(lifetime, config.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    def test_expired_token_rejected(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES + 5)
        token, _ = security.create_access_token("user-123", now=old)
        with self.assertRaises(security.InvalidTokenError):
            security.decode_access_token(token)

    def test_tampered_payload_rejected(self):
        token, _ = security.create_access_token("user-123")
        header, payload, sig = token.split(".")
        forged = jwt.encode({"sub": "someone-else", "iat": 1, "exp": 9999999999}, "wrong-key" * 5, algorithm="HS256")
        with self.assertRaises(security.InvalidTokenError):
            security.decode_access_token(forged)
        with self.assertRaises(security.InvalidTokenError):
            security.decode_access_token(f"{header}.{payload}x.{sig}")

    def test_alg_none_rejected(self):
        unsigned = jwt.encode({"sub": "user-123", "iat": 1, "exp": 9999999999}, key=None, algorithm="none")
        with self.assertRaises(security.InvalidTokenError):
            security.decode_access_token(unsigned)

    def test_other_hmac_algorithm_rejected(self):
        key = config.JWT_SECRET_KEY
        other = jwt.encode({"sub": "user-123", "iat": 1, "exp": 9999999999}, key, algorithm="HS512")
        with self.assertRaises(security.InvalidTokenError):
            security.decode_access_token(other)

    def test_token_without_required_claims_rejected(self):
        key = config.JWT_SECRET_KEY
        for claims in (
            {"iat": 1, "exp": 9999999999},           # no sub
            {"sub": "u", "iat": 1},                  # no exp -> would never expire
            {"sub": "u", "exp": 9999999999},         # no iat
        ):
            with self.assertRaises(security.InvalidTokenError, msg=str(claims)):
                security.decode_access_token(jwt.encode(claims, key, algorithm="HS256"))

    def test_garbage_rejected(self):
        for bad in ["", "abc", "a.b.c", "Bearer x"]:
            with self.assertRaises(security.InvalidTokenError):
                security.decode_access_token(bad)

    def test_missing_or_short_secret_fails_loudly(self):
        original = config.JWT_SECRET_KEY
        try:
            for bad in (None, "", "too-short"):
                config.JWT_SECRET_KEY = bad
                with self.assertRaises(RuntimeError):
                    security.create_access_token("u")
                with self.assertRaises(RuntimeError):
                    security.assert_auth_configured()
        finally:
            config.JWT_SECRET_KEY = original


class ThrottleTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.t = LoginThrottle(max_failures=3, window_seconds=60, clock=lambda: self.now)

    def test_allows_until_limit_then_blocks(self):
        for _ in range(2):
            self.t.record_failure("k")
        self.assertEqual(self.t.retry_after("k"), 0)
        self.t.record_failure("k")
        self.assertGreater(self.t.retry_after("k"), 0)

    def test_block_expires_with_the_window(self):
        for _ in range(3):
            self.t.record_failure("k")
        self.now += 61
        self.assertEqual(self.t.retry_after("k"), 0)

    def test_keys_are_independent(self):
        for _ in range(3):
            self.t.record_failure("attacker|victim@x.com")
        self.assertGreater(self.t.retry_after("attacker|victim@x.com"), 0)
        self.assertEqual(self.t.retry_after("someone-else|victim@x.com"), 0)

    def test_success_clears_failures(self):
        for _ in range(2):
            self.t.record_failure("k")
        self.t.reset("k")
        for _ in range(2):
            self.t.record_failure("k")
        self.assertEqual(self.t.retry_after("k"), 0)


if __name__ == "__main__":
    unittest.main()
