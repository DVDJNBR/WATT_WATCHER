"""
Tests for Story 4.2 — API Key Authentication

Covers: _load_api_key caching, require_auth decorator (AC #1, #2, #3).
"""

import json
import os
import uuid
from unittest.mock import patch, MagicMock

import pytest

from shared.api.auth import require_auth, reset_api_key


# ─── Helpers ──────────────────────────────────────────────────────────────────

class MockRequest:
    """Minimal mock for func.HttpRequest."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.method = "GET"


class MockHandler:
    """Handler that records calls."""

    def __init__(self, return_value=None):
        self.calls = []
        self._return_value = return_value

    def __call__(self, req):
        self.calls.append(req)
        return self._return_value or {"status_code": 200, "body": "ok"}


VALID_KEY = "test-api-key-abc123"


@pytest.fixture(autouse=True)
def clear_api_key_cache():
    """Reset cached key between tests."""
    reset_api_key()
    yield
    reset_api_key()


def _decorated_with_env_key(key=VALID_KEY):
    """Return a decorated handler with key set via env var."""
    handler = MockHandler()
    decorated = require_auth(handler)
    return decorated, handler


# ─── AC #1: Missing / invalid key → 401 ──────────────────────────────────────

class TestMissingOrInvalidKey:

    def test_missing_header_returns_401(self):
        """AC #1: No X-Api-Key header → 401."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(handler.calls) == 0

    def test_empty_header_returns_401(self):
        """AC #1: Empty X-Api-Key value → 401."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": ""})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(handler.calls) == 0

    def test_wrong_key_returns_401(self):
        """AC #1: Wrong key → 401."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": "wrong-key"})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(handler.calls) == 0

    def test_401_body_has_request_id(self):
        """401 response body includes a valid UUID request_id."""
        decorated, _ = _decorated_with_env_key()
        req = MockRequest(headers={})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        body = json.loads(resp.get_body())
        assert "request_id" in body
        assert uuid.UUID(body["request_id"])  # raises if invalid UUID

    def test_401_body_has_error_fields(self):
        """401 response body includes standard error fields."""
        decorated, _ = _decorated_with_env_key()
        req = MockRequest(headers={})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        body = json.loads(resp.get_body())
        assert body["status_code"] == 401
        assert body["error"] == "Unauthorized"
        assert "message" in body

    def test_401_has_www_authenticate_header(self):
        """401 response includes WWW-Authenticate: ApiKey header."""
        decorated, _ = _decorated_with_env_key()
        req = MockRequest(headers={})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert "WWW-Authenticate" in resp.headers
        assert "ApiKey" in resp.headers["WWW-Authenticate"]

    def test_401_has_x_request_id_header(self):
        """401 response includes X-Request-Id header."""
        decorated, _ = _decorated_with_env_key()
        req = MockRequest(headers={})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert "X-Request-Id" in resp.headers


# ─── AC #2: Valid key → handler called ───────────────────────────────────────

class TestValidKey:

    def test_valid_key_calls_handler(self):
        """AC #2: Correct X-Api-Key → handler is called."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": VALID_KEY})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert len(handler.calls) == 1
        assert handler.calls[0] is req

    def test_valid_key_returns_handler_response(self):
        """AC #2: Handler return value is passed through."""
        handler = MockHandler(return_value={"status_code": 200, "body": "data"})
        decorated = require_auth(handler)
        req = MockRequest(headers={"X-Api-Key": VALID_KEY})

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            resp = decorated(req)

        assert resp == {"status_code": 200, "body": "data"}


# ─── Key loading ──────────────────────────────────────────────────────────────

class TestKeyLoading:

    def test_key_loaded_from_env_var(self):
        """Falls back to API_KEY env var when KEY_VAULT_URL is absent."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": VALID_KEY})

        env = {"API_KEY": VALID_KEY}
        env.pop("KEY_VAULT_URL", None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("KEY_VAULT_URL", None)
            resp = decorated(req)

        assert len(handler.calls) == 1

    def test_key_cached_after_first_load(self):
        """API key is loaded only once (cached module-level)."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": VALID_KEY})

        call_count = 0
        original_environ_get = os.environ.get

        def counting_get(key, default=None):
            nonlocal call_count
            if key == "API_KEY":
                call_count += 1
            return original_environ_get(key, default)

        with patch.dict(os.environ, {"API_KEY": VALID_KEY}):
            with patch.object(os.environ, "get", side_effect=counting_get):
                decorated(req)
                first_count = call_count
                decorated(req)
                second_count = call_count

        # Second call should not re-read the env var
        assert second_count == first_count

    def test_key_loaded_from_key_vault_when_configured(self):
        """Key Vault takes priority over env var when KEY_VAULT_URL is set."""
        KV_KEY = "keyvault-secret-key"
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": KV_KEY})

        mock_kv = MagicMock()
        mock_kv.get_secret.return_value = KV_KEY

        env = {"KEY_VAULT_URL": "https://watt-watcher-key-vault.vault.azure.net/", "API_KEY": "fallback"}
        with patch.dict(os.environ, env):
            with patch("shared.keyvault.KeyVaultClient", return_value=mock_kv):
                resp = decorated(req)

        assert len(handler.calls) == 1
        mock_kv.get_secret.assert_called_once_with("API-KEY")

    def test_misconfigured_env_returns_401(self):
        """No API_KEY env var and no Key Vault → 401 (not 500)."""
        decorated, handler = _decorated_with_env_key()
        req = MockRequest(headers={"X-Api-Key": "some-key"})

        with patch.dict(os.environ, {}, clear=True):
            # Ensure neither API_KEY nor KEY_VAULT_URL are set
            os.environ.pop("API_KEY", None)
            os.environ.pop("KEY_VAULT_URL", None)
            resp = decorated(req)

        assert resp.status_code == 401
        assert len(handler.calls) == 0

    def test_reset_api_key_clears_cache(self):
        """reset_api_key() forces reload on next call."""
        from shared.api.auth import _load_api_key

        with patch.dict(os.environ, {"API_KEY": "key-v1"}):
            key1 = _load_api_key()

        reset_api_key()

        with patch.dict(os.environ, {"API_KEY": "key-v2"}):
            key2 = _load_api_key()

        assert key1 == "key-v1"
        assert key2 == "key-v2"


# ─── AC #3: Applied to all non-public endpoints ───────────────────────────────

class TestRoutesAuth:
    def test_public_routes_defined(self):
        from shared.api.routes import PUBLIC_ROUTES, ROUTE_HEALTH
        assert ROUTE_HEALTH in PUBLIC_ROUTES

    def test_protected_routes_not_public(self):
        from shared.api.routes import PUBLIC_ROUTES, ROUTE_PRODUCTION, ROUTE_EXPORT
        assert ROUTE_PRODUCTION not in PUBLIC_ROUTES
        assert ROUTE_EXPORT not in PUBLIC_ROUTES
