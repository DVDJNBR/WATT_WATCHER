"""
API Key Authentication — Story 4.2

Validates the X-Api-Key header against the secret stored in Key Vault.
Falls back to the API_KEY environment variable for local development.

AC #1: 401 on missing/invalid X-Api-Key header.
AC #2: Valid key → handler called.
AC #3: Applied to all non-public endpoints.
"""

import functools
import json
import logging
import os
import uuid
from typing import Any, Callable, Optional

import jwt

logger = logging.getLogger(__name__)

# Module-level cache — loaded once per cold start
_api_key: Optional[str] = None


def _load_api_key() -> str:
    """
    Load the API key from Key Vault (production) or env var (local dev).
    Cached after first load.
    """
    global _api_key
    if _api_key is not None:
        return _api_key

    # Try Key Vault first (production)
    key_vault_url = os.environ.get("KEY_VAULT_URL")
    if key_vault_url:
        try:
            from shared.keyvault import KeyVaultClient
            kv = KeyVaultClient(vault_url=key_vault_url)
            value = kv.get_secret("API-KEY")
            if value:
                _api_key = value
                logger.info("API key loaded from Key Vault")
                return _api_key
        except Exception as exc:
            logger.warning("Could not load API key from Key Vault: %s", exc)

    # Fallback: env var (local dev)
    value = os.environ.get("API_KEY", "")
    if not value:
        raise EnvironmentError("API key not configured (Key Vault: API-KEY or env: API_KEY)")

    _api_key = value
    logger.info("API key loaded from environment variable")
    return _api_key


def reset_api_key() -> None:
    """Clear cached key — used in tests."""
    global _api_key
    _api_key = None


# ─── @require_auth decorator ─────────────────────────────────────────────────

def require_auth(handler: Callable) -> Callable:
    """
    Decorator that enforces API key authentication on HTTP trigger handlers.

    Clients must send:  X-Api-Key: <key>

    AC #1: Missing or wrong key → 401.
    AC #2: Valid key → handler called.
    """
    @functools.wraps(handler)
    def wrapper(req: Any) -> Any:
        request_id = str(uuid.uuid4())

        provided_key = ""
        if hasattr(req, "headers"):
            provided_key = req.headers.get("X-Api-Key", "")

        if not provided_key:
            return _make_401("Missing X-Api-Key header", request_id)

        try:
            expected_key = _load_api_key()
        except EnvironmentError as exc:
            logger.error("Auth config error [%s]: %s", request_id, exc)
            return _make_401("Authentication service misconfigured", request_id)

        if not _secure_compare(provided_key, expected_key):
            return _make_401("Invalid API key", request_id)

        return handler(req)

    return wrapper


def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


def _make_401(message: str, request_id: str, www_authenticate: str = 'ApiKey realm="watt-watcher"') -> Any:
    """Build a 401 response.

    Args:
        www_authenticate: Value for the WWW-Authenticate header.
            Defaults to ApiKey scheme (require_auth).
            Pass 'Bearer realm="watt-watcher"' for JWT endpoints (require_jwt).
    """
    body = json.dumps({
        "request_id": request_id,
        "status_code": 401,
        "error": "Unauthorized",
        "message": message,
        "details": {},
    })
    headers = {
        "X-Request-Id": request_id,
        "WWW-Authenticate": www_authenticate,
    }

    try:
        import azure.functions as func  # type: ignore[import]
        return func.HttpResponse(
            body, status_code=401, mimetype="application/json", headers=headers,
        )
    except ImportError:
        return _Response(body=body, status_code=401, headers=headers)


class _Response:
    """Lightweight response object used when azure.functions is unavailable."""

    def __init__(self, body: str, status_code: int, headers: dict):
        self._body = body
        self.status_code = status_code
        self.headers = headers
        self.mimetype = "application/json"

    def get_body(self) -> bytes:
        return self._body.encode("utf-8") if isinstance(self._body, str) else self._body


# ─── JWT Authentication ───────────────────────────────────────────────────────

# Module-level cache — loaded once per cold start
_jwt_secret: Optional[str] = None


def _load_jwt_secret() -> str:
    """
    Load the JWT secret from Key Vault (production) or env var (local dev).
    Cached after first load.
    """
    global _jwt_secret
    if _jwt_secret is not None:
        return _jwt_secret

    # Try Key Vault first (production)
    key_vault_url = os.environ.get("KEY_VAULT_URL")
    if key_vault_url:
        try:
            from shared.keyvault import KeyVaultClient
            kv = KeyVaultClient(vault_url=key_vault_url)
            value = kv.get_secret("JWT_SECRET")
            if value:
                _jwt_secret = value
                logger.info("JWT secret loaded from Key Vault")
                return _jwt_secret
        except Exception as exc:
            logger.warning("Could not load JWT secret from Key Vault: %s", exc)

    # Fallback: env var (local dev)
    value = os.environ.get("JWT_SECRET", "")
    if not value:
        raise EnvironmentError("JWT secret not configured (Key Vault: JWT_SECRET or env: JWT_SECRET)")

    _jwt_secret = value
    logger.info("JWT secret loaded from environment variable")
    return _jwt_secret


def reset_jwt_secret() -> None:
    """Clear cached secret — used in tests."""
    global _jwt_secret
    _jwt_secret = None


def require_jwt(handler: Callable) -> Callable:
    """
    Decorator that enforces JWT authentication on HTTP trigger handlers.

    Clients must send:  Authorization: Bearer <jwt_token>

    If valid, calls handler(req, user={"user_id": ..., "email": ...})
    Returns 401 for missing header, invalid format, expired or malformed token.
    """
    _JWT_WWW_AUTH = 'Bearer realm="watt-watcher"'

    @functools.wraps(handler)
    def wrapper(req: Any) -> Any:
        request_id = str(uuid.uuid4())

        auth_header = ""
        if hasattr(req, "headers"):
            auth_header = req.headers.get("Authorization", "")

        if not auth_header:
            return _make_401("Missing Authorization header", request_id, _JWT_WWW_AUTH)

        if not auth_header.startswith("Bearer "):
            return _make_401("Invalid Authorization header format", request_id, _JWT_WWW_AUTH)

        token = auth_header.split(" ", 1)[1]

        try:
            secret = _load_jwt_secret()
        except EnvironmentError as exc:
            logger.error("JWT config error [%s]: %s", request_id, exc)
            return _make_401("Authentication service misconfigured", request_id, _JWT_WWW_AUTH)

        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return _make_401("Token has expired", request_id, _JWT_WWW_AUTH)
        except jwt.InvalidTokenError:
            return _make_401("Invalid token", request_id, _JWT_WWW_AUTH)

        user = {"user_id": payload.get("user_id"), "email": payload.get("email")}
        return handler(req, user=user)

    return wrapper
