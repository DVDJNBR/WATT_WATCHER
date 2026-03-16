"""
Tests for Story 2.1 — JWT Middleware

Covers: require_jwt decorator (valid token, expired, absent, malformed,
        non-Bearer format, misconfigured secret).
"""

import datetime
import json
import os
import uuid

import jwt
import pytest

from shared.api.auth import require_jwt, reset_jwt_secret


# ─── Constants & helpers ──────────────────────────────────────────────────────

JWT_SECRET = "test-jwt-secret-for-unit-tests-32b"  # ≥ 32 bytes for HS256


def _make_token(payload: dict, secret: str = JWT_SECRET) -> str:
    """Encode a JWT token with the given payload and secret."""
    return jwt.encode(payload, secret, algorithm="HS256")


def _valid_payload(offset_hours: int = 24) -> dict:
    return {
        "user_id": 42,
        "email": "user@test.com",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=offset_hours),
    }


def _expired_payload() -> dict:
    return {
        "user_id": 42,
        "email": "user@test.com",
        "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=1),
    }


class MockRequest:
    """Minimal mock for func.HttpRequest."""
    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}
        self.method = "GET"


def _make_handler():
    """Return a handler that records calls, and its calls list."""
    calls = []

    def handler(req, user=None):
        calls.append({"req": req, "user": user})
        return {"status_code": 200}

    return handler, calls


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_jwt_cache():
    """Reset cached JWT secret between tests."""
    reset_jwt_secret()
    yield
    reset_jwt_secret()


# ─── AC: Token valide → handler appelé avec user= ────────────────────────────

class TestValidToken:

    def test_valid_token_calls_handler(self):
        """Valid Bearer token → handler is called exactly once."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            decorated(req)

        assert len(calls) == 1

    def test_valid_token_injects_user_id(self):
        """Valid token → handler receives user_id from payload."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            decorated(req)

        assert calls[0]["user"]["user_id"] == 42

    def test_valid_token_injects_email(self):
        """Valid token → handler receives email from payload."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            decorated(req)

        assert calls[0]["user"]["email"] == "user@test.com"

    def test_valid_token_returns_handler_response(self):
        """Valid token → handler return value is passed through."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            result = decorated(req)

        assert result == {"status_code": 200}

    def test_valid_token_request_id_in_response_on_success(self):
        """functools.wraps preserves handler name."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        assert decorated.__name__ == handler.__name__


# ─── AC: Token expiré → 401 ───────────────────────────────────────────────────

class TestExpiredToken:

    def test_expired_token_returns_401(self):
        """Expired token → 401 Unauthorized."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_expired_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_expired_token_body_message(self):
        """Expired token → response body indicates expiry."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_expired_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        body = json.loads(resp.get_body())
        assert "expired" in body["message"].lower()


# ─── AC: Token absent → 401 ───────────────────────────────────────────────────

class TestMissingToken:

    def test_missing_header_returns_401(self):
        """No Authorization header → 401."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_missing_header_body_has_request_id(self):
        """401 body includes valid UUID request_id."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        body = json.loads(resp.get_body())
        assert "request_id" in body
        assert uuid.UUID(body["request_id"])  # raises if not valid UUID

    def test_missing_header_body_structure(self):
        """401 body has standard error fields."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        body = json.loads(resp.get_body())
        assert body["status_code"] == 401
        assert body["error"] == "Unauthorized"
        assert "message" in body

    def test_401_has_bearer_www_authenticate_header(self):
        """JWT 401 must advertise Bearer scheme, not ApiKey (RFC 6750)."""
        handler, _ = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert "WWW-Authenticate" in resp.headers
        assert resp.headers["WWW-Authenticate"].startswith("Bearer")


# ─── AC: Token malformé → 401 ────────────────────────────────────────────────

class TestMalformedToken:

    def test_random_string_returns_401(self):
        """Random string as token → 401."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={"Authorization": "Bearer not.a.valid.jwt"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_wrong_secret_returns_401(self):
        """Token signed with different secret → 401."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload(), secret="wrong-secret")
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_non_bearer_scheme_returns_401(self):
        """Authorization: Basic abc → 401 (not Bearer scheme)."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={"Authorization": "Basic dXNlcjpwYXNz"})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_empty_bearer_token_returns_401(self):
        """Authorization: Bearer (empty) → 401."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        req = MockRequest(headers={"Authorization": "Bearer "})

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0


# ─── Secret non configuré → 401 (pas 500) ────────────────────────────────────

class TestMisconfiguredSecret:

    def test_missing_secret_returns_401_not_500(self):
        """No JWT_SECRET env var and no Key Vault → 401, not 500."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.MonkeyPatch().context() as mp:
            mp.delenv("JWT_SECRET", raising=False)
            mp.delenv("KEY_VAULT_URL", raising=False)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(calls) == 0

    def test_reset_jwt_secret_forces_reload(self):
        """reset_jwt_secret() clears cache so next call re-reads env var."""
        handler, calls = _make_handler()
        decorated = require_jwt(handler)
        token = _make_token(_valid_payload())
        req = MockRequest(headers={"Authorization": f"Bearer {token}"})

        # First call with secret v1 — should fail (wrong secret)
        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", "wrong-secret")
            resp1 = decorated(req)
        assert resp1.status_code == 401

        reset_jwt_secret()

        # Second call with correct secret — should succeed
        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("JWT_SECRET", JWT_SECRET)
            resp2 = decorated(req)
        assert resp2 == {"status_code": 200}
