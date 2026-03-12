# Story 2.2: Register & Email Confirmation Endpoints

Status: done

## Story

As a new user,
I want to register with email and password and confirm my account via email,
so that I can access the platform.

## Acceptance Criteria

1. `POST /v1/auth/register` : crée compte avec bcrypt cost=12, envoie email de confirmation, retourne 201
2. `POST /v1/auth/confirm` : active le compte via token UUID v4, invalide le token après usage, retourne 200
3. `POST /v1/auth/resend-confirmation` : renvoie l'email si compte non confirmé, retourne 200
4. Email non confirmé → login impossible (retourne 403 avec message explicite) — **Note :** login sera implémenté en story 2.3 ; cette AC est documentée ici pour que `auth_service.py` porte le guard, pas story 2.3
5. Token confirmation expire après 1h
6. Email déjà existant → 409 Conflict
7. Validation format email côté serveur

## Tasks / Subtasks

- [x] Ajouter bcrypt aux dépendances (précondition)
  - [x] Ajouter `bcrypt>=4.1.0` dans `pyproject.toml` [dependencies]
  - [x] Ajouter `bcrypt>=4.1.0` dans `requirements.txt`
  - [x] Installer dans le venv : bcrypt 5.0.0 installé via pip --target
- [x] Migration 004 — ajouter `confirmation_token_expires` (AC: 5)
  - [x] Créer `functions/migrations/004_add_confirmation_token_expires.sql`
  - [x] Colonne `confirmation_token_expires DATETIME2 NULL`
  - [x] Idempotente (`IF NOT EXISTS` sur la colonne)
- [x] Mettre à jour `functions/shared/api/error_handlers.py` (AC: 6)
  - [x] Ajouter `409: "Conflict"` dans `_STATUS_LABELS`
  - [x] Ajouter helper `conflict(message, request_id)` → `error_response(409, message, request_id)`
- [x] Ajouter routes dans `functions/shared/api/routes.py` (AC: 1-3)
  - [x] `ROUTE_AUTH_REGISTER = "v1/auth/register"`
  - [x] `ROUTE_AUTH_CONFIRM = "v1/auth/confirm"`
  - [x] `ROUTE_AUTH_RESEND = "v1/auth/resend-confirmation"`
- [x] Créer `functions/shared/api/email_service.py` (AC: 1, 3)
  - [x] Classe `EmailService` avec méthode `send_confirmation(to_email: str, token: str) -> None`
  - [x] Mode mock activable via env var `EMAIL_MOCK=true` (log au lieu d'envoyer)
  - [x] Intégration Resend en mode réel : `requests.post` vers `https://api.resend.com/emails`
  - [x] Clé API Resend chargée depuis Key Vault (`RESEND_API_KEY`) ou env var `RESEND_API_KEY`
  - [x] **Note :** story 5.1 étendra `EmailService` avec `send_reset()` et `send_alert()`
- [x] Créer `functions/shared/api/auth_service.py` (AC: 1-7)
  - [x] `register(conn, email, password) -> dict` (AC: 1, 6, 7)
  - [x] `confirm_email(conn, token) -> dict` (AC: 2, 5)
  - [x] `resend_confirmation(conn, email, email_service) -> dict` (AC: 3)
  - [x] Helper `_is_email_valid(email: str) -> bool` (AC: 7)
- [x] Ajouter 3 endpoints dans `functions/function_app.py` (AC: 1-3)
  - [x] `POST /v1/auth/register` → appelle `register()`, retourne 201
  - [x] `POST /v1/auth/confirm` → appelle `confirm_email()`, retourne 200
  - [x] `POST /v1/auth/resend-confirmation` → appelle `resend_confirmation()`, retourne 200
- [x] Écrire les tests dans `tests/test_register_confirmation.py` (AC: 1-7)
  - [x] register → 201, token généré, email envoyé (mock)
  - [x] register avec email dupliqué → 409
  - [x] register avec email invalide → 400
  - [x] confirm avec token valide → 200, `is_confirmed=1`, token effacé
  - [x] confirm avec token expiré → 400
  - [x] confirm avec token inconnu → 400
  - [x] confirm avec token déjà utilisé → 400
  - [x] resend sur compte non confirmé → 200, nouvel email envoyé
  - [x] resend sur compte déjà confirmé → 400
  - [x] resend sur email inconnu → 200 (pas de leak)

## Dev Notes

### ⚠️ Précondition : bcrypt

Vérifier d'abord si bcrypt est disponible :

```bash
.venv/bin/python -c "import bcrypt; print(bcrypt.__version__)"
# si ModuleNotFoundError :
python3.11 -m pip install --target .venv/lib/python3.11/site-packages "bcrypt>=4.1.0"
```

bcrypt est NOT dans le venv (confirmé). Contrairement à PyJWT, bcrypt n'est probablement pas disponible system-wide non plus.

### Migration 004 — confirmation_token_expires

La table `USER_ACCOUNT` (migration 001) a `confirmation_token NVARCHAR(500)` mais **pas de colonne d'expiry pour ce token**.
`reset_token_expires DATETIME2` existe pour les tokens de reset — il faut la même chose pour la confirmation.

```sql
-- functions/migrations/004_add_confirmation_token_expires.sql
-- Migration 004: Add confirmation_token_expires to USER_ACCOUNT
-- Idempotent: safe to run multiple times

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME='USER_ACCOUNT' AND COLUMN_NAME='confirmation_token_expires'
)
    ALTER TABLE USER_ACCOUNT
    ADD confirmation_token_expires DATETIME2 NULL;
```

**SQLite fallback** (tests locaux) : SQLite ne supporte pas `IF NOT EXISTS` sur ALTER TABLE. Dans les tests, utiliser `try/except` ou créer la table entière avec la colonne.

### error_handlers.py — ajouter 409

```python
# Ajouter dans _STATUS_LABELS :
409: "Conflict",

# Ajouter helper :
def conflict(message: str, request_id: Optional[str] = None) -> dict:
    """409 — resource already exists."""
    return error_response(409, message, request_id)
```

### routes.py — nouvelles routes

```python
# Auth endpoints (public — pas de @require_auth, pas de @require_jwt)
ROUTE_AUTH_REGISTER = "v1/auth/register"
ROUTE_AUTH_CONFIRM = "v1/auth/confirm"
ROUTE_AUTH_RESEND = "v1/auth/resend-confirmation"
```

### email_service.py — implémentation minimale

```python
# functions/shared/api/email_service.py
"""
Email Service — Story 2.2 (minimal: send_confirmation only)
Story 5.1 étendra cette classe avec send_reset() et send_alert().
"""
import logging
import os
from typing import Optional

import requests  # déjà dans requirements.txt

logger = logging.getLogger(__name__)

_resend_api_key: Optional[str] = None

CONFIRMATION_URL_BASE = os.environ.get("APP_BASE_URL", "https://watt-watcher.fr")


def _load_resend_api_key() -> str:
    global _resend_api_key
    if _resend_api_key is not None:
        return _resend_api_key

    key_vault_url = os.environ.get("KEY_VAULT_URL")
    if key_vault_url:
        try:
            from shared.keyvault import KeyVaultClient
            kv = KeyVaultClient(vault_url=key_vault_url)
            value = kv.get_secret("RESEND_API_KEY")
            if value:
                _resend_api_key = value
                return _resend_api_key
        except Exception as exc:
            logger.warning("Could not load RESEND_API_KEY from Key Vault: %s", exc)

    value = os.environ.get("RESEND_API_KEY", "")
    if not value:
        raise EnvironmentError("RESEND_API_KEY not configured")
    _resend_api_key = value
    return _resend_api_key


def reset_resend_api_key() -> None:
    """Clear cached key — used in tests."""
    global _resend_api_key
    _resend_api_key = None


class EmailService:

    def send_confirmation(self, to_email: str, token: str) -> None:
        """
        Send account confirmation email with token link.

        In mock mode (EMAIL_MOCK=true), logs instead of sending.
        """
        confirm_url = f"{CONFIRMATION_URL_BASE}/confirm?token={token}"

        if os.environ.get("EMAIL_MOCK", "").lower() == "true":
            logger.info(
                "EMAIL_MOCK: send_confirmation to=%s url=%s", to_email, confirm_url
            )
            return

        api_key = _load_resend_api_key()
        payload = {
            "from": "WATT WATCHER <noreply@watt-watcher.fr>",
            "to": [to_email],
            "subject": "Confirmez votre compte WATT WATCHER",
            "html": (
                f"<p>Bienvenue sur WATT WATCHER !</p>"
                f"<p><a href='{confirm_url}'>Confirmer mon compte</a></p>"
                f"<p>Ce lien expire dans 1h.</p>"
            ),
        }
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if not resp.ok:
            logger.error("Resend API error %d: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Email send failed: {resp.status_code}")
        logger.info("Confirmation email sent to %s", to_email)
```

### auth_service.py — implémentation

```python
# functions/shared/api/auth_service.py
"""
Auth Service — Story 2.2
Handles register, confirm_email, resend_confirmation.
Login/logout/reset/delete will be added in stories 2.3/2.4/2.5.
"""
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import bcrypt

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
TOKEN_EXPIRY_HOURS = 1


def _is_email_valid(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email)) and len(email) <= 255


def register(conn: Any, email: str, password: str, email_service) -> dict:
    """
    Register a new user account.

    Returns: {"user_id": int, "email": str}
    Raises:
        ValueError: invalid email format
        ConflictError: email already exists
    """
    if not _is_email_valid(email):
        raise ValueError("Invalid email format")

    email = email.lower().strip()

    cursor = conn.cursor()

    # Check for duplicate
    cursor.execute("SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,))
    if cursor.fetchone():
        raise ConflictError("Email already registered")

    # Hash password
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    # Generate confirmation token
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

    cursor.execute(
        """
        INSERT INTO USER_ACCOUNT
            (email, password_hash, is_confirmed, confirmation_token, confirmation_token_expires)
        VALUES (?, ?, 0, ?, ?)
        """,
        (email, password_hash, token, expires),
    )
    conn.commit()

    # Fetch the new user_id
    cursor.execute("SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,))
    row = cursor.fetchone()
    user_id = row[0]

    # Send confirmation email (fire-and-forget — don't fail registration if email fails)
    try:
        email_service.send_confirmation(email, token)
    except Exception as exc:
        logger.error("Failed to send confirmation email to %s: %s", email, exc)

    return {"user_id": user_id, "email": email}


def confirm_email(conn: Any, token: str) -> dict:
    """
    Confirm a user's email via token.

    Returns: {"user_id": int, "email": str}
    Raises:
        TokenError: token not found, expired, or already used
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, email, is_confirmed, confirmation_token_expires
        FROM USER_ACCOUNT
        WHERE confirmation_token = ?
        """,
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        raise TokenError("Invalid or unknown confirmation token")

    user_id, email, is_confirmed, expires = row

    if is_confirmed:
        raise TokenError("Token already used — account already confirmed")

    if expires and datetime.utcnow() > _parse_datetime(expires):
        raise TokenError("Confirmation token has expired")

    # Activate account and invalidate token
    cursor.execute(
        """
        UPDATE USER_ACCOUNT
        SET is_confirmed = 1,
            confirmation_token = NULL,
            confirmation_token_expires = NULL
        WHERE id = ?
        """,
        (user_id,),
    )
    conn.commit()

    return {"user_id": user_id, "email": email}


def resend_confirmation(conn: Any, email: str, email_service) -> dict:
    """
    Resend confirmation email for an unconfirmed account.

    Always returns 200 even if email not found (no information leak).
    Raises:
        AlreadyConfirmedError: account is already confirmed
    """
    email = email.lower().strip()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, is_confirmed FROM USER_ACCOUNT WHERE email = ?", (email,)
    )
    row = cursor.fetchone()

    if not row:
        # Don't leak that email doesn't exist — silently return
        return {"message": "If the account exists, a confirmation email has been sent"}

    user_id, is_confirmed = row

    if is_confirmed:
        raise AlreadyConfirmedError("Account is already confirmed")

    # Generate new token and expiry
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    cursor.execute(
        "UPDATE USER_ACCOUNT SET confirmation_token = ?, confirmation_token_expires = ? WHERE id = ?",
        (token, expires, user_id),
    )
    conn.commit()

    try:
        email_service.send_confirmation(email, token)
    except Exception as exc:
        logger.error("Failed to resend confirmation email to %s: %s", email, exc)

    return {"message": "If the account exists, a confirmation email has been sent"}


def _parse_datetime(value) -> datetime:
    """Parse datetime from DB — handles both datetime objects and strings."""
    if isinstance(value, datetime):
        return value
    # pyodbc returns datetime directly; sqlite3 returns string
    return datetime.fromisoformat(str(value))


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ConflictError(Exception):
    """Email already registered."""

class TokenError(Exception):
    """Token invalid, expired, or already used."""

class AlreadyConfirmedError(Exception):
    """Account is already confirmed — resend not applicable."""
```

### function_app.py — 3 nouveaux endpoints

**Imports à ajouter en haut :**

```python
from shared.api.routes import (
    ROUTE_PRODUCTION, ROUTE_EXPORT, ROUTE_HEALTH, ROUTE_DOCS,
    ROUTE_OPENAPI_JSON, ROUTE_ALERTS,
    ROUTE_AUTH_REGISTER, ROUTE_AUTH_CONFIRM, ROUTE_AUTH_RESEND,  # ← new
)
from shared.api.error_handlers import bad_request, not_found, server_error, conflict  # ← add conflict
from shared.api.auth_service import (  # ← new
    register, confirm_email, resend_confirmation,
    ConflictError, TokenError, AlreadyConfirmedError,
)
from shared.api.email_service import EmailService  # ← new
```

**Endpoints :**

```python
# ── Story 2.2: Auth — Register ───────────────────────────────────────────
@app.route(route=ROUTE_AUTH_REGISTER, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_register(req: func.HttpRequest) -> func.HttpResponse:
    """POST /v1/auth/register — create new user account."""
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    email = body.get("email", "").strip() if body else ""
    password = body.get("password", "") if body else ""

    if not email or not password:
        return func.HttpResponse(
            json.dumps(bad_request("email and password are required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    try:
        conn = _get_db_connection()
        svc = EmailService()
        result = register(conn, email, password, svc)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "user_id": result["user_id"], "email": result["email"]}),
            status_code=201, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except ValueError as exc:
        return func.HttpResponse(
            json.dumps(bad_request(str(exc), request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except ConflictError as exc:
        return func.HttpResponse(
            json.dumps(conflict(str(exc), request_id)),
            status_code=409, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("register error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )


# ── Story 2.2: Auth — Confirm ────────────────────────────────────────────
@app.route(route=ROUTE_AUTH_CONFIRM, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_confirm(req: func.HttpRequest) -> func.HttpResponse:
    """POST /v1/auth/confirm — confirm email with token."""
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    token = body.get("token", "").strip() if body else ""
    if not token:
        return func.HttpResponse(
            json.dumps(bad_request("token is required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    try:
        conn = _get_db_connection()
        result = confirm_email(conn, token)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "message": "Account confirmed", "user_id": result["user_id"]}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except TokenError as exc:
        return func.HttpResponse(
            json.dumps(bad_request(str(exc), request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("confirm error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )


# ── Story 2.2: Auth — Resend confirmation ────────────────────────────────
@app.route(route=ROUTE_AUTH_RESEND, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_resend(req: func.HttpRequest) -> func.HttpResponse:
    """POST /v1/auth/resend-confirmation — resend confirmation email."""
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    email = body.get("email", "").strip() if body else ""
    if not email:
        return func.HttpResponse(
            json.dumps(bad_request("email is required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    try:
        conn = _get_db_connection()
        svc = EmailService()
        result = resend_confirmation(conn, email, svc)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "message": result["message"]}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except AlreadyConfirmedError as exc:
        return func.HttpResponse(
            json.dumps(bad_request(str(exc), request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("resend error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
```

### Pattern des tests

Tests dans `tests/test_register_confirmation.py`. Les tests utilisent SQLite en mémoire avec le schéma `USER_ACCOUNT` (incluant `confirmation_token_expires` de la migration 004).

```python
import sqlite3, datetime, json, uuid
import pytest
from unittest.mock import MagicMock, patch
from shared.api.auth_service import (
    register, confirm_email, resend_confirmation,
    ConflictError, TokenError, AlreadyConfirmedError,
)

def _make_db():
    """In-memory SQLite with USER_ACCOUNT schema (matches Azure SQL)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmation_token TEXT,
            confirmation_token_expires TEXT,
            reset_token TEXT,
            reset_token_expires TEXT,
            last_activity TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    return conn

def _make_email_service():
    """Mock EmailService that records calls."""
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    return svc
```

**Tests clés :**

```python
def test_register_creates_account():
    conn = _make_db()
    svc = _make_email_service()
    result = register(conn, "user@test.com", "password123", svc)
    assert result["email"] == "user@test.com"
    assert result["user_id"] is not None
    svc.send_confirmation.assert_called_once()

def test_register_duplicate_raises_conflict():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    with pytest.raises(ConflictError):
        register(conn, "user@test.com", "password456", svc)

def test_register_invalid_email_raises_value_error():
    conn = _make_db()
    svc = _make_email_service()
    with pytest.raises(ValueError):
        register(conn, "notanemail", "password123", svc)

def test_confirm_valid_token():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    token = conn.execute("SELECT confirmation_token FROM USER_ACCOUNT").fetchone()[0]
    result = confirm_email(conn, token)
    assert result["email"] == "user@test.com"
    row = conn.execute("SELECT is_confirmed, confirmation_token FROM USER_ACCOUNT").fetchone()
    assert row[0] == 1
    assert row[1] is None  # token invalidated

def test_confirm_expired_token():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    # Expire the token retroactively
    conn.execute("UPDATE USER_ACCOUNT SET confirmation_token_expires = ?",
                 (datetime.datetime.utcnow() - datetime.timedelta(hours=2),))
    conn.commit()
    token = conn.execute("SELECT confirmation_token FROM USER_ACCOUNT").fetchone()[0]
    with pytest.raises(TokenError, match="expired"):
        confirm_email(conn, token)

def test_confirm_unknown_token_raises():
    conn = _make_db()
    with pytest.raises(TokenError):
        confirm_email(conn, "unknown-token")

def test_confirm_already_confirmed_raises():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    token = conn.execute("SELECT confirmation_token FROM USER_ACCOUNT").fetchone()[0]
    confirm_email(conn, token)
    with pytest.raises(TokenError, match="already confirmed"):
        confirm_email(conn, token)

def test_resend_unconfirmed_account():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    svc.send_confirmation.reset_mock()
    result = resend_confirmation(conn, "user@test.com", svc)
    assert "confirmation email" in result["message"]
    svc.send_confirmation.assert_called_once()

def test_resend_unknown_email_returns_200_no_leak():
    conn = _make_db()
    svc = _make_email_service()
    result = resend_confirmation(conn, "unknown@test.com", svc)
    assert "confirmation email" in result["message"]
    svc.send_confirmation.assert_not_called()

def test_resend_already_confirmed_raises():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)
    token = conn.execute("SELECT confirmation_token FROM USER_ACCOUNT").fetchone()[0]
    confirm_email(conn, token)
    with pytest.raises(AlreadyConfirmedError):
        resend_confirmation(conn, "user@test.com", svc)
```

### SQLite vs Azure SQL — différences importantes

| Particularité | Azure SQL (pyodbc) | SQLite (tests) |
|---|---|---|
| Placeholder | `?` | `?` ✅ même |
| DATETIME2 | native | stocké comme TEXT |
| `conn.commit()` | nécessaire | nécessaire |
| `cursor.lastrowid` | non dispo pyodbc | disponible |
| Récupérer user_id après INSERT | `SELECT id WHERE email=?` | même méthode ✅ |

**Note :** Pour récupérer l'`id` après INSERT avec pyodbc, ne pas utiliser `cursor.lastrowid` — il retourne toujours None. Utiliser `SELECT id FROM USER_ACCOUNT WHERE email = ?` juste après le commit.

### bcrypt API (v4.x)

```python
import bcrypt

# Hash
password_hash = bcrypt.hashpw(b"password123", bcrypt.gensalt(rounds=12))
# → bytes. Stocker comme .decode("utf-8") dans la DB.

# Verify (story 2.3 — login)
bcrypt.checkpw(b"password123", password_hash)
# → bool
```

### References

- [Source: functions/migrations/001_create_user_account.sql] — schéma USER_ACCOUNT existant (⚠️ pas de confirmation_token_expires — besoin migration 004)
- [Source: functions/shared/api/auth.py] — pattern Key Vault, `_load_*`, `reset_*`, `_Response`
- [Source: functions/function_app.py] — pattern Azure Functions v4, `_get_db_connection()`, `@app.route()`
- [Source: functions/shared/api/error_handlers.py] — `error_response()` à étendre avec 409
- [Source: functions/shared/api/routes.py] — convention `ROUTE_*` sans leading slash
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security] — bcrypt cost=12, UUID v4, 1h expiry
- [Source: _bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 2.2] — ACs

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- bcrypt 5.0.0 installé (système n'avait pas `_cffi_backend` — pip --target utilisé, même pattern que PyJWT)
- Migration 004 créée pour `confirmation_token_expires` — colonne absente de migration 001
- `error_handlers.py` étendu : `403: "Forbidden"`, `409: "Conflict"`, helper `conflict()`
- `email_service.py` créé avec `send_confirmation()` + mode mock `EMAIL_MOCK=true` + Key Vault pattern
- `auth_service.py` : register / confirm_email / resend_confirmation + 3 exceptions custom
- Token invalidé par NULL après confirmation — test ajusté : deuxième confirm → "Invalid or unknown" (comportement correct, le token n'existe plus)
- Email send failure fire-and-forget dans register() et resend_confirmation() — la registration/resend réussit même si Resend est down
- 32/32 tests nouveaux, 318/318 suite complète, 0 régression
- CR fixes: H1 TOCTOU → catch IntegrityError dans register(); H2 conn.close() dans finally pour 3 endpoints; M1 normalize-before-validate; M2 tests/test_email_service.py ajouté (8 tests); M3 assertion token vérifiée depuis DB
- 326/326 après CR fixes, 0 régression

### File List

- `functions/migrations/004_add_confirmation_token_expires.sql`
- `functions/shared/api/email_service.py`
- `functions/shared/api/auth_service.py`
- `functions/shared/api/error_handlers.py`
- `functions/shared/api/routes.py`
- `functions/function_app.py`
- `tests/test_register_confirmation.py`
- `tests/test_email_service.py`
- `pyproject.toml`
- `requirements.txt`
