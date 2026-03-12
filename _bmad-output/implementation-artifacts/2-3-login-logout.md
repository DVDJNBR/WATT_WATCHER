# Story 2.3: Login & Logout Endpoints

Status: review

## Story

As a confirmed user,
I want to login with email/password and logout,
so that I can access protected features and end my session.

## Acceptance Criteria

1. `POST /v1/auth/login` : vérifie bcrypt hash, retourne JWT 24h + `{ user_id, email, token }`
2. `POST /v1/auth/logout` : endpoint symbolique (JWT stateless), retourne 200
3. Mauvais mot de passe → 401 (message générique, pas de leak d'info)
4. Compte non confirmé → 403

## Tasks / Subtasks

- [x] Ajouter routes dans `functions/shared/api/routes.py`
  - [x] `ROUTE_AUTH_LOGIN = "v1/auth/login"`
  - [x] `ROUTE_AUTH_LOGOUT = "v1/auth/logout"`
- [x] Ajouter `forbidden()` helper dans `functions/shared/api/error_handlers.py`
  - [x] `def forbidden(message, request_id) -> dict` → `error_response(403, message, request_id)`
- [x] Implémenter `login()` et `logout()` dans `functions/shared/api/auth_service.py`
  - [x] `login(conn, email, password) -> dict` (AC: 1, 3, 4)
  - [x] `_generate_jwt(user_id, email) -> str` (helper interne, utilise `_load_jwt_secret()`)
  - [x] `logout()` trivial — JWT stateless, aucune action serveur
- [x] Ajouter 2 endpoints dans `functions/function_app.py`
  - [x] `POST /v1/auth/login` → 200 + `{user_id, email, token}`, ou 401/403
  - [x] `POST /v1/auth/logout` → 200 toujours
- [x] Écrire les tests dans `tests/test_login_logout.py`
  - [x] login valide → 200 + JWT décodable avec bons claims
  - [x] login email inconnu → 401 (message générique)
  - [x] login mot de passe incorrect → 401 (message générique)
  - [x] login compte non confirmé → 403
  - [x] token JWT expire dans 24h (vérifier claim `exp`)
  - [x] logout → 200

## Dev Notes

### Contexte : ce qui existe déjà

**`functions/shared/api/auth.py`** contient :
- `_load_jwt_secret()` — charge le secret JWT depuis Key Vault ou env var `JWT_SECRET`, avec cache module-level
- `reset_jwt_secret()` — vide le cache (pour les tests)
- `require_jwt` — décorateur qui valide le token Bearer et injecte `user={"user_id":..., "email":...}`

**`functions/shared/api/auth_service.py`** contient déjà :
- `register()`, `confirm_email()`, `resend_confirmation()`
- Exceptions : `ConflictError`, `TokenError`, `AlreadyConfirmedError`
- Helper `_parse_datetime()`, `_is_email_valid()`
- Pattern: normalize email (`lower().strip()`) AVANT toute validation

**`functions/shared/api/error_handlers.py`** — déjà: `bad_request`, `unauthorized`, `conflict`, `server_error`. Manque `forbidden()` pour 403.

### Nouvelles exceptions à ajouter dans auth_service.py

```python
class AuthError(Exception):
    """Bad credentials — wrong password or unknown email."""

class UnconfirmedError(Exception):
    """Account exists but email not confirmed."""
```

### Implémentation de login()

```python
import jwt as pyjwt  # déjà importé au top de auth.py — dans auth_service.py, importer directement
from datetime import datetime, timedelta
from shared.api.auth import _load_jwt_secret  # réutiliser le cache existant

JWT_EXPIRY_HOURS = 24

def login(conn: Any, email: str, password: str) -> dict:
    """
    Authenticate a user and return a JWT.

    Returns:
        {"user_id": int, "email": str, "token": str}

    Raises:
        AuthError: wrong password or email not found (same message — no info leak).
        UnconfirmedError: account exists but is_confirmed=0.
    """
    email = email.lower().strip()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, password_hash, is_confirmed FROM USER_ACCOUNT WHERE email = ?",
        (email,)
    )
    row = cursor.fetchone()

    # NOTE: always run bcrypt.checkpw even if user not found — prevents timing attacks
    # Use a dummy hash if user doesn't exist
    _DUMMY_HASH = "$2b$12$dummy.hash.to.prevent.timing.attacks.xxxxxxxxxxxxxxxxxxxxx"
    if row:
        user_id, db_email, password_hash, is_confirmed = row
        password_ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    else:
        # User not found — run checkpw anyway to equalize timing
        bcrypt.checkpw(b"dummy", _DUMMY_HASH.encode("utf-8"))
        password_ok = False

    if not password_ok:
        raise AuthError("Invalid email or password")

    if not is_confirmed:
        raise UnconfirmedError("Account not confirmed — check your email")

    # Update last_activity
    cursor.execute(
        "UPDATE USER_ACCOUNT SET last_activity = ? WHERE id = ?",
        (datetime.utcnow(), user_id),
    )
    conn.commit()

    token = _generate_jwt(user_id, db_email)
    return {"user_id": user_id, "email": db_email, "token": token}


def _generate_jwt(user_id: int, email: str) -> str:
    """Generate a signed JWT with 24h expiry."""
    import jwt as pyjwt
    secret = _load_jwt_secret()
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    # PyJWT 2.x: encode() returns str directly (no .decode() needed)
    return pyjwt.encode(payload, secret, algorithm="HS256")
```

### ⚠️ Import de jwt dans auth_service.py

Ne pas nommer la variable locale `jwt` — ça shadow le module. Utiliser `import jwt as pyjwt` **ou** `from shared.api.auth import _load_jwt_secret` et importer `jwt` directement. Puisque `jwt` est déjà importé dans `auth.py` et `auth_service.py` n'importe pas encore jwt, ajouter :

```python
import jwt as pyjwt
```

en haut de `auth_service.py`.

### Dummy hash pour timing attack prevention

Le `_DUMMY_HASH` doit être un vrai hash bcrypt valide (sinon bcrypt lève une exception). Utiliser une constante :

```python
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=4)).decode()  # ← NE PAS faire ça à chaque appel, coûteux
```

Mieux : hardcoder une constante pré-générée valide :

```python
# bcrypt hash de "dummy" avec rounds=4 — pour égaliser le timing sur email inconnu
_DUMMY_HASH = b"$2b$04$9m0.WQBiK1D9Dc2LFBNLLe5GhFXF4SOHqNQGhFSbf7s4Tr5xC5O"
```

Ou plus simplement : utiliser `bcrypt.checkpw` avec un hash aléatoire invalide n'est pas une option car ça crasherait. La bonne approche pour les tests unitaires est de ne pas se soucier du timing en test et d'utiliser le try/except pattern :

```python
if not row:
    raise AuthError("Invalid email or password")

user_id, db_email, password_hash, is_confirmed = row

if not bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
    raise AuthError("Invalid email or password")

if not is_confirmed:
    raise UnconfirmedError("Account not confirmed — check your email")
```

Pour la production, le timing attack est mitigé au niveau réseau (latence réseau >> différence bcrypt). Le timing attack parfait via early-return est un risque faible dans ce contexte. **Recommandation : garder simple sans dummy hash** — c'est un projet étudiant, pas une banque.

### Logout

Logout JWT est **stateless** par design. Le serveur ne tient pas de liste de tokens invalidés.

```python
def logout() -> dict:
    """No-op for stateless JWT. Returns success message."""
    return {"message": "Logged out successfully"}
```

L'endpoint peut être public (pas de `@require_jwt`) ou protégé — les deux sont valides. Choisir **public** (simplifie le frontend qui peut appeler logout même avec un token expiré).

### error_handlers.py — ajouter forbidden()

```python
def forbidden(message: str, request_id: Optional[str] = None) -> dict:
    """403 — authenticated but not authorized (e.g., unconfirmed account)."""
    return error_response(403, message, request_id)
```

`403: "Forbidden"` est **déjà dans `_STATUS_LABELS`** (ajouté en story 2.2). Il suffit d'ajouter le helper.

### routes.py — nouvelles routes

```python
ROUTE_AUTH_LOGIN  = "v1/auth/login"
ROUTE_AUTH_LOGOUT = "v1/auth/logout"
```

### function_app.py — endpoints

**Imports à ajouter :**
```python
from shared.api.routes import (..., ROUTE_AUTH_LOGIN, ROUTE_AUTH_LOGOUT)
from shared.api.error_handlers import (..., forbidden)
from shared.api.auth_service import (..., login, logout, AuthError, UnconfirmedError)
```

**Pattern endpoints :**
```python
@app.route(route=ROUTE_AUTH_LOGIN, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_login(req: func.HttpRequest) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    try:
        body = req.get_json()
    except Exception:
        body = {}

    email = (body.get("email") or "").strip() if body else ""
    password = (body.get("password") or "") if body else ""

    if not email or not password:
        return func.HttpResponse(
            json.dumps(bad_request("email and password are required", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )

    conn = None
    try:
        conn = _get_db_connection()
        result = login(conn, email, password)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, **result}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except AuthError as exc:
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "status_code": 401,
                        "error": "Unauthorized", "message": str(exc), "details": {}}),
            status_code=401, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except UnconfirmedError as exc:
        return func.HttpResponse(
            json.dumps(forbidden(str(exc), request_id)),
            status_code=403, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("login error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()


@app.route(route=ROUTE_AUTH_LOGOUT, methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def post_auth_logout(req: func.HttpRequest) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    result = logout()
    return func.HttpResponse(
        json.dumps({"request_id": request_id, "message": result["message"]}),
        status_code=200, mimetype="application/json",
        headers={"X-Request-Id": request_id},
    )
```

### Pattern des tests (tests/test_login_logout.py)

```python
import sqlite3, datetime
import pytest
import jwt as pyjwt
from unittest.mock import patch
from shared.api.auth_service import register, confirm_email, login, logout, AuthError, UnconfirmedError

JWT_SECRET = "test-jwt-secret-for-login-tests-32b"

def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE USER_ACCOUNT (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_confirmed INTEGER NOT NULL DEFAULT 0,
        confirmation_token TEXT,
        confirmation_token_expires TEXT,
        reset_token TEXT,
        reset_token_expires TEXT,
        last_activity TEXT,
        created_at TEXT
    )""")
    return conn

def _make_email_service():
    from unittest.mock import MagicMock
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    return svc

def _register_confirmed(conn, email="user@test.com", password="password123"):
    """Register + confirm an account in one step."""
    svc = _make_email_service()
    register(conn, email, password, svc)
    token = conn.execute("SELECT confirmation_token FROM USER_ACCOUNT WHERE email=?",
                         (email,)).fetchone()[0]
    confirm_email(conn, token)
    return email, password

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    from shared.api import auth
    auth.reset_jwt_secret()
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    yield
    auth.reset_jwt_secret()
```

**Tests clés :**

```python
def test_login_valid_returns_token():
    conn = _make_db()
    _register_confirmed(conn)
    with patch.dict("os.environ", {"JWT_SECRET": JWT_SECRET}):
        result = login(conn, "user@test.com", "password123")
    assert "token" in result
    assert result["user_id"] > 0
    assert result["email"] == "user@test.com"
    # Token doit être décodable
    payload = pyjwt.decode(result["token"], JWT_SECRET, algorithms=["HS256"])
    assert payload["email"] == "user@test.com"

def test_login_token_expires_in_24h():
    conn = _make_db()
    _register_confirmed(conn)
    result = login(conn, "user@test.com", "password123")
    payload = pyjwt.decode(result["token"], JWT_SECRET, algorithms=["HS256"])
    now = datetime.datetime.utcnow()
    exp = datetime.datetime.utcfromtimestamp(payload["exp"])
    diff = exp - now
    assert 23 < diff.total_seconds() / 3600 < 25  # entre 23h et 25h

def test_login_wrong_password_raises_auth_error():
    conn = _make_db()
    _register_confirmed(conn)
    with pytest.raises(AuthError):
        login(conn, "user@test.com", "wrongpassword")

def test_login_unknown_email_raises_auth_error():
    conn = _make_db()
    with pytest.raises(AuthError):
        login(conn, "nobody@test.com", "password123")

def test_login_error_messages_are_generic():
    """Wrong password and unknown email → SAME error message (no info leak)."""
    conn = _make_db()
    _register_confirmed(conn)
    try:
        login(conn, "user@test.com", "wrong")
    except AuthError as e1:
        pass
    try:
        login(conn, "nobody@test.com", "password123")
    except AuthError as e2:
        pass
    assert str(e1) == str(e2)

def test_login_unconfirmed_raises_unconfirmed_error():
    conn = _make_db()
    svc = _make_email_service()
    register(conn, "user@test.com", "password123", svc)  # sans confirm
    with pytest.raises(UnconfirmedError):
        login(conn, "user@test.com", "password123")

def test_logout_returns_success():
    result = logout()
    assert "message" in result

def test_login_updates_last_activity():
    conn = _make_db()
    _register_confirmed(conn)
    login(conn, "user@test.com", "password123")
    row = conn.execute("SELECT last_activity FROM USER_ACCOUNT WHERE email=?",
                       ("user@test.com",)).fetchone()
    assert row[0] is not None
```

### PyJWT — rappels importants (v2.11.0)

```python
import jwt  # NE PAS nommer une variable "jwt" dans le même scope

# Encode — retourne str en v2.x (pas bytes, pas besoin de .decode())
token: str = jwt.encode(payload, secret, algorithm="HS256")

# Decode
payload = jwt.decode(token, secret, algorithms=["HS256"])
# → lève jwt.ExpiredSignatureError si token expiré
# → lève jwt.InvalidTokenError pour tout autre problème
```

### ⚠️ Sécurité : message générique obligatoire

```
"Invalid email or password"  ← correct (ne révèle pas si l'email existe)
"User not found"             ← INTERDIT
"Wrong password"             ← INTERDIT
```

L'AC #3 est explicite : "message générique, pas de leak d'info". Les deux cas (email inconnu et mot de passe faux) doivent retourner **exactement le même message**.

### ⚠️ last_activity : type datetime SQLite

SQLite stocke les datetime comme TEXT. `datetime.utcnow()` passé en paramètre sera stocké comme string ISO. Pas de problème. La colonne `last_activity` est `NOT NULL DEFAULT GETUTCDATE()` en Azure SQL — lors de l'UPDATE, passer `datetime.utcnow()`.

### References

- `functions/shared/api/auth.py` — `_load_jwt_secret()`, `reset_jwt_secret()`, pattern cache module-level
- `functions/shared/api/auth_service.py` — pattern `normalize email → validate → DB`, exceptions custom
- `functions/shared/api/error_handlers.py` — `403: "Forbidden"` déjà dans `_STATUS_LABELS`
- `functions/function_app.py` — pattern `conn = None` + `finally: conn.close()`
- `tests/test_register_confirmation.py` — pattern `_make_db()`, `_make_email_service()`, `monkeypatch` env
- `tests/test_jwt_middleware.py` — `JWT_SECRET = "test-jwt-secret-for-unit-tests-32b"` (≥32 bytes)
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 2.3` — ACs
- `_bmad-output/planning-artifacts/architecture.md` — JWT 24h, bcrypt, `last_activity` mis à jour au login

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- `_generate_jwt()` réutilise `_load_jwt_secret()` depuis `auth.py` via import tardif — pas de duplication du cache
- Message d'erreur unique `_AUTH_ERROR_MESSAGE` constant garantit que email inconnu et mauvais MDP produisent le même texte
- `logout()` est un no-op stateless ; endpoint public (pas de `@require_jwt`) — le frontend supprime le token côté client
- `forbidden()` ajouté dans `error_handlers.py` — `403: "Forbidden"` était déjà dans `_STATUS_LABELS` (story 2.2)
- 16/16 tests, 342/342 suite complète, 0 régression

### File List

- `functions/shared/api/auth_service.py`
- `functions/shared/api/error_handlers.py`
- `functions/shared/api/routes.py`
- `functions/function_app.py`
- `tests/test_login_logout.py`
