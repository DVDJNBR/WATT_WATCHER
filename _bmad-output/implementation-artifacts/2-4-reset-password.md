# Story 2.4: Reset Password Endpoints

Status: done

## Story

As a user who forgot their password,
I want to reset it via email link,
so that I can regain access to my account.

## Acceptance Criteria

1. `POST /v1/auth/reset-password/request` : envoie email avec token reset si email connu — retourne **toujours 200** avec un message générique (pas de leak sur l'existence du compte)
2. `POST /v1/auth/reset-password/confirm` : applique le nouveau mot de passe via token, invalide le token, retourne 200
3. Token reset expire après 1h et est à usage unique (invalidé après utilisation)
4. Nouveau mot de passe hashé avec bcrypt cost=12

## Tasks / Subtasks

- [x] Ajouter `send_reset()` dans `functions/shared/api/email_service.py` (AC: 1)
  - [x] Méthode `send_reset(self, to_email: str, token: str)` — pattern identique à `send_confirmation`
  - [x] Mock mode : logger.info au lieu d'appeler Resend
  - [x] URL reset : `{self._base_url}/reset-password?token={token}`
- [x] Ajouter routes dans `functions/shared/api/routes.py` (AC: 1, 2)
  - [x] `ROUTE_AUTH_RESET_REQUEST = "v1/auth/reset-password/request"`
  - [x] `ROUTE_AUTH_RESET_CONFIRM = "v1/auth/reset-password/confirm"`
- [x] Implémenter `request_password_reset()` dans `functions/shared/api/auth_service.py` (AC: 1, 3)
  - [x] Normaliser email (`lower().strip()`)
  - [x] Lookup email en BDD — si absent : retourner message générique silencieusement
  - [x] Générer UUID v4 token + expiry `datetime.now(timezone.utc) + timedelta(hours=1)`
  - [x] UPDATE USER_ACCOUNT SET reset_token, reset_token_expires WHERE id=?
  - [x] `email_service.send_reset(email, token)` — fire-and-forget (try/except, logger.error si échec)
  - [x] Retourner `{"message": "If the account exists, a reset email has been sent"}`
- [x] Implémenter `confirm_password_reset()` dans `functions/shared/api/auth_service.py` (AC: 2, 3, 4)
  - [x] Lookup par `reset_token` → `TokenError` si non trouvé
  - [x] Vérifier `reset_token_expires` → `TokenError` si expiré (utiliser `_parse_datetime()`)
  - [x] Valider `new_password` non-vide → `ValueError` si vide
  - [x] Hasher le nouveau mdp : `bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt(rounds=12))`
  - [x] UPDATE USER_ACCOUNT SET password_hash=?, reset_token=NULL, reset_token_expires=NULL, last_activity=? WHERE id=?
  - [x] Retourner `{"user_id": int, "email": str}`
- [x] Ajouter 2 endpoints dans `functions/function_app.py` (AC: 1, 2)
  - [x] `POST /v1/auth/reset-password/request` → toujours 200 (pas d'exception à propager vers le client)
  - [x] `POST /v1/auth/reset-password/confirm` → 200 ou 400 (ValueError) ou 400 (TokenError)
- [x] Écrire les tests dans `tests/test_reset_password.py`
  - [x] `request_password_reset` email connu → message générique retourné
  - [x] `request_password_reset` email inconnu → même message générique (no info leak)
  - [x] `request_password_reset` → `send_reset` appelé avec l'email et le token
  - [x] `request_password_reset` email inconnu → `send_reset` NOT called
  - [x] `request_password_reset` echec email send → ne pas propager l'exception
  - [x] `confirm_password_reset` token valide → 200, nouveau mdp fonctionnel (login après reset OK)
  - [x] `confirm_password_reset` token inconnu → `TokenError`
  - [x] `confirm_password_reset` token expiré → `TokenError`
  - [x] `confirm_password_reset` token déjà utilisé → `TokenError`
  - [x] `confirm_password_reset` → reset_token NULLé après usage
  - [x] `confirm_password_reset` → last_activity mis à jour
  - [x] `confirm_password_reset` mdp vide → `ValueError`
  - [x] `confirm_password_reset` nouveau mdp correctement hashé (login fonctionne ensuite)
- [x] Étendre `tests/test_email_service.py` — couvrir `send_reset()` mock mode (AC: 1)
  - [x] `send_reset` mock mode → pas d'appel HTTP, log info

## Dev Notes

### Contexte : ce qui existe déjà

**`functions/shared/api/auth_service.py`** contient :
- `TOKEN_EXPIRY_HOURS = 1` — réutiliser pour le reset token
- `_parse_datetime(value)` — normalise datetime pyodbc/sqlite3 → toujours utiliser pour comparer avec expiry
- `_is_email_valid(email)` — pas nécessaire ici (l'email vient de l'utilisateur qui veut reset, on cherche juste en BDD)
- `TokenError` — **déjà défini** (story 2.2) — réutiliser tel quel pour token invalide/expiré/déjà utilisé
- `_DUMMY_HASH` — pas utile ici (pas de vérification de mot de passe en entrée)
- `from datetime import datetime, timedelta, timezone` — import complet disponible

**`functions/shared/api/email_service.py`** :
- Docstring indique "Story 5.1 will extend this class with send_reset()" MAIS story 2.4 en a besoin
- Ajouter `send_reset()` maintenant (story 5.1 n'ajoutera que `send_alert()`)
- Pattern identique à `send_confirmation()` : mock check → log si mock → Resend si prod
- `self._base_url` et `self._from_address` disponibles

**`functions/shared/api/error_handlers.py`** — déjà : `bad_request`, `unauthorized`, `forbidden`, `conflict`, `server_error`

**`functions/function_app.py`** — patterns établis :
```python
conn = None
try:
    conn = _get_db_connection()
    result = service_function(conn, ...)
    return func.HttpResponse(json.dumps({...}), status_code=200, ...)
except SpecificError as exc:
    return func.HttpResponse(json.dumps(bad_request(str(exc), request_id)), status_code=400, ...)
except Exception as exc:
    logger.error("reset error [%s]: %s", request_id, exc, exc_info=True)
    return func.HttpResponse(json.dumps(server_error(request_id=request_id)), status_code=500, ...)
finally:
    if conn:
        conn.close()
```

### Schema USER_ACCOUNT — colonnes reset (déjà présentes)

```sql
reset_token          TEXT     NULL,
reset_token_expires  TEXT     NULL,
```
Vérifier dans `functions/migrations/001_create_user_account.sql` que ces colonnes existent. Si absent → ajouter migration `005_add_reset_token.sql` avec `IF NOT EXISTS` (même pattern que migration 004 pour `confirmation_token_expires`).

### Implémentation de `request_password_reset()`

```python
def request_password_reset(conn: Any, email: str, email_service: Any) -> dict:
    """
    Initiate password reset flow.

    Security: always returns the same message whether the email exists or not
    (no information leak about registered emails).

    Returns:
        {"message": str}
    """
    email = email.lower().strip()

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,))
    row = cursor.fetchone()

    if not row:
        # Silent return — don't reveal whether email is registered
        return {"message": "If the account exists, a reset email has been sent"}

    user_id = row[0]
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    cursor.execute(
        "UPDATE USER_ACCOUNT SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
        (token, expires, user_id),
    )
    conn.commit()

    # Fire-and-forget — email failure doesn't abort the flow
    try:
        email_service.send_reset(email, token)
    except Exception as exc:
        logger.error("Failed to send reset email to %s: %s", email, exc, exc_info=True)

    return {"message": "If the account exists, a reset email has been sent"}
```

### Implémentation de `confirm_password_reset()`

```python
def confirm_password_reset(conn: Any, token: str, new_password: str) -> dict:
    """
    Apply new password via reset token.

    Returns:
        {"user_id": int, "email": str}

    Raises:
        TokenError: token not found, expired, or already used.
        ValueError: new_password is empty.
    """
    if not token:
        raise TokenError("Reset token is required")
    if not new_password:
        raise ValueError("New password cannot be empty")

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, reset_token_expires FROM USER_ACCOUNT WHERE reset_token = ?",
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        raise TokenError("Invalid or unknown reset token")

    user_id, email, expires_raw = row

    if expires_raw is not None:
        expires = _parse_datetime(expires_raw)
        # Make expires timezone-aware if it's naive (from older DB rows)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise TokenError("Reset token has expired")

    # Hash new password
    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    cursor.execute(
        """
        UPDATE USER_ACCOUNT
        SET password_hash = ?,
            reset_token = NULL,
            reset_token_expires = NULL,
            last_activity = ?
        WHERE id = ?
        """,
        (password_hash, datetime.now(timezone.utc), user_id),
    )
    conn.commit()

    return {"user_id": user_id, "email": email}
```

### ⚠️ Subtilité timezone — `_parse_datetime()` et sqlite3

`_parse_datetime()` fait `datetime.fromisoformat(str(value))`. Si la valeur stockée en BDD est une datetime timezone-aware (de `datetime.now(timezone.utc)`), sqlite3 retourne une string comme `"2026-03-11 14:30:00+00:00"` → `fromisoformat` retourne un datetime aware. La comparaison `datetime.now(timezone.utc) > expires` est alors aware vs aware → OK.

Mais si des tokens ont été générés avec `datetime.utcnow()` (naive), la string sqlite sera `"2026-03-11 14:30:00.123456"` → `fromisoformat` retourne naive → comparaison naive vs aware → **TypeError**. Protection : utiliser le `.replace(tzinfo=timezone.utc)` guard montré ci-dessus.

### `send_reset()` dans EmailService

```python
def send_reset(self, to_email: str, token: str) -> None:
    """
    Send password reset email with token link.

    Args:
        to_email: Recipient email address.
        token: UUID v4 reset token.
    """
    reset_url = f"{self._base_url}/reset-password?token={token}"

    if self._mock:
        logger.info(
            "EMAIL_MOCK send_reset: to=%s reset_url=%s",
            to_email,
            reset_url,
        )
        return

    api_key = _load_resend_api_key()
    payload = {
        "from": self._from_address,
        "to": [to_email],
        "subject": "Réinitialisation de votre mot de passe WATT WATCHER",
        "html": (
            f"<p>Vous avez demandé la réinitialisation de votre mot de passe.</p>"
            f"<p><a href='{reset_url}'>Réinitialiser mon mot de passe</a></p>"
            f"<p>Ce lien expire dans 1 heure. Si vous n'avez pas fait cette demande, ignorez cet email.</p>"
        ),
    }
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    if not resp.ok:
        logger.error("Resend API error %d: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Email send failed (status={resp.status_code})")
    logger.info("Reset email sent to %s", to_email)
```

### Endpoints dans function_app.py

**Imports à ajouter :**
```python
from shared.api.routes import (..., ROUTE_AUTH_RESET_REQUEST, ROUTE_AUTH_RESET_CONFIRM)
from shared.api.auth_service import (..., request_password_reset, confirm_password_reset)
# TokenError est déjà importé depuis story 2.2
```

**POST /v1/auth/reset-password/request** — toujours 200 :
```python
@app.route(route=ROUTE_AUTH_RESET_REQUEST, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_reset_request(req: func.HttpRequest) -> func.HttpResponse:
    """POST /v1/auth/reset-password/request — initiate password reset (always 200)."""
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    email = (body.get("email") or "").strip() if body else ""

    if not email:
        return func.HttpResponse(
            json.dumps(bad_request("email is required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    email_svc = EmailService()
    conn = None
    try:
        conn = _get_db_connection()
        result = request_password_reset(conn, email, email_svc)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, **result}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("reset-request error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()
```

**POST /v1/auth/reset-password/confirm** — 200 ou 400 :
```python
@app.route(route=ROUTE_AUTH_RESET_CONFIRM, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_reset_confirm(req: func.HttpRequest) -> func.HttpResponse:
    """POST /v1/auth/reset-password/confirm — apply new password via token."""
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    token = (body.get("token") or "").strip() if body else ""
    new_password = (body.get("new_password") or "") if body else ""

    if not token or not new_password:
        return func.HttpResponse(
            json.dumps(bad_request("token and new_password are required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    conn = None
    try:
        conn = _get_db_connection()
        result = confirm_password_reset(conn, token, new_password)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, **result}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except (TokenError, ValueError) as exc:
        return func.HttpResponse(
            json.dumps(bad_request(str(exc), request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("reset-confirm error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()
```

### Pattern des tests (tests/test_reset_password.py)

```python
"""Tests for Story 2.4 — Reset Password."""
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import bcrypt
import pytest

from shared.api.auth_service import (
    TokenError,
    confirm_password_reset,
    login,
    register,
    confirm_email,
    request_password_reset,
)


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE USER_ACCOUNT (
            id                          INTEGER  PRIMARY KEY AUTOINCREMENT,
            email                       TEXT     NOT NULL UNIQUE,
            password_hash               TEXT     NOT NULL,
            is_confirmed                INTEGER  NOT NULL DEFAULT 0,
            confirmation_token          TEXT,
            confirmation_token_expires  TEXT,
            reset_token                 TEXT,
            reset_token_expires         TEXT,
            last_activity               TEXT,
            created_at                  TEXT
        )
    """)
    return conn


def _make_email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    svc.send_reset = MagicMock()
    return svc


def _register_confirmed(conn, email="user@test.com", password="password123"):
    svc = _make_email_service()
    register(conn, email, password, svc)
    token = conn.execute(
        "SELECT confirmation_token FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]
    confirm_email(conn, token)
```

**⚠️ JWT secret fixture** : `request_password_reset` et `confirm_password_reset` n'utilisent PAS `_load_jwt_secret()` → pas besoin du `set_jwt_secret` fixture. Mais les tests qui vérify que le login fonctionne après reset en auront besoin. Utiliser `autouse=False` et ne l'inclure que là où c'est nécessaire.

### Vérifier migration 001

Avant tout, vérifier que `functions/migrations/001_create_user_account.sql` contient `reset_token` et `reset_token_expires`. Si absent → créer `005_add_reset_token.sql` :
```sql
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'USER_ACCOUNT' AND COLUMN_NAME = 'reset_token'
)
    ALTER TABLE USER_ACCOUNT ADD reset_token TEXT NULL;

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'USER_ACCOUNT' AND COLUMN_NAME = 'reset_token_expires'
)
    ALTER TABLE USER_ACCOUNT ADD reset_token_expires DATETIME2 NULL;
```

### References

- `functions/shared/api/auth_service.py` — `TOKEN_EXPIRY_HOURS`, `_parse_datetime()`, `TokenError`, `_is_email_valid()`, pattern normalize-email-first
- `functions/shared/api/email_service.py` — classe `EmailService`, `send_confirmation()` (modèle à répliquer pour `send_reset`)
- `functions/shared/api/error_handlers.py` — `bad_request`, `server_error`
- `functions/shared/api/routes.py` — pattern `ROUTE_AUTH_*`
- `functions/function_app.py` — pattern `conn = None` + `finally: conn.close()`, `EmailService()` instantiation
- `functions/migrations/001_create_user_account.sql` — vérifier colonnes `reset_token`, `reset_token_expires`
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 2.4` — ACs source
- `_bmad-output/planning-artifacts/architecture.md` — tokens 1h usage unique, bcrypt cost≥12, no info leak

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Migration 001 déjà complète — `reset_token` et `reset_token_expires` présents, aucune migration 005 nécessaire
- `send_reset()` ajouté à `EmailService` (story 5.1 n'ajoutera que `send_alert()`)
- `request_password_reset()` : no-info-leak garanti — même message pour email connu/inconnu ; email send fire-and-forget
- `confirm_password_reset()` : guard timezone pour datetimes naïves stockées par d'anciens appels `utcnow()`
- `TokenError` réutilisé tel quel depuis story 2.2 pour les cas token inconnu/expiré/déjà utilisé
- 29 nouveaux tests (test_reset_password.py x27 + test_email_service.py x2) — 372/372 suite complète, 0 régression

### File List

- `functions/shared/api/email_service.py`
- `functions/shared/api/routes.py`
- `functions/shared/api/auth_service.py`
- `functions/function_app.py`
- `tests/test_reset_password.py`
- `tests/test_email_service.py`
