# Story 2.1: JWT Middleware

Status: done

## Story

As a developer,
I want a reusable `@require_jwt` decorator for Azure Functions,
so that protected endpoints can validate tokens consistently.

## Acceptance Criteria

1. Décorateur `@require_jwt` ajouté dans `functions/shared/api/auth.py` — **additif**, `require_auth` (API Key) reste inchangé
2. Vérifie le header `Authorization: Bearer <token>` — retourne 401 si header absent ou mal formé
3. Retourne 401 si token invalide (mauvaise signature, malformé, expiré)
4. Si token valide, injecte le payload décodé via `user` kwarg : `handler(req, user={"user_id": ..., "email": ...})`
5. Utilise PyJWT avec algorithme HS256 exclusivement
6. Secret JWT chargé depuis Key Vault (clé `JWT_SECRET`) avec fallback env var `JWT_SECRET`
7. Tests unitaires couvrent : token valide, token expiré, token absent, token malformé

## Tasks / Subtasks

- [x] Ajouter PyJWT aux dépendances (AC: 5)
  - [x] Ajouter `PyJWT>=2.8.0` dans `pyproject.toml` [dependencies]
  - [x] Ajouter `PyJWT>=2.8.0` dans `requirements.txt`
  - [x] Installer dans le venv : `.venv/bin/pip install "PyJWT>=2.8.0"`
- [x] Implémenter `require_jwt` dans `functions/shared/api/auth.py` (AC: 1-6)
  - [x] Ajouter `_load_jwt_secret()` et `reset_jwt_secret()` (pattern identique à `_load_api_key`)
  - [x] Implémenter le décorateur `@require_jwt` : extract Bearer token, decode, inject `user`
  - [x] Gérer les cas d'erreur : header absent, format non-Bearer, `ExpiredSignatureError`, `InvalidTokenError`
- [x] Écrire les tests dans `tests/test_jwt_middleware.py` (AC: 7)
  - [x] Token valide → handler appelé avec `user={"user_id": ..., "email": ...}`
  - [x] Token expiré → 401
  - [x] Header absent → 401
  - [x] Token malformé → 401
  - [x] Header non-Bearer (ex: `Basic abc`) → 401
  - [x] Secret non configuré → 401 (pas 500)
- [x] Vérifier aucune régression sur `tests/test_auth.py` (AC: 1)

## Dev Notes

### ⚠️ PyJWT PAS dans le venv — installer EN PREMIER

```bash
# Ajouter aux deux fichiers de dépendances PUIS installer
.venv/bin/pip install "PyJWT>=2.8.0"
```

PyJWT est présent system-wide (`/usr/lib/python3/dist-packages`, v2.7.0) mais **pas dans le venv du projet**. Les tests s'exécutent avec `.venv/bin/python` — sans installation venv, `import jwt` lèvera `ModuleNotFoundError`.

### Architecture de `require_auth` existant (à NE PAS modifier)

```python
# auth.py — pattern existant à préserver tel quel
_api_key: Optional[str] = None

def _load_api_key() -> str: ...     # Key Vault → env var API_KEY
def reset_api_key() -> None: ...    # cache clear pour tests
def require_auth(handler): ...      # @functools.wraps, vérifie X-Api-Key
def _secure_compare(a, b): ...      # hmac.compare_digest
def _make_401(message, request_id): ...
class _Response: ...                # fallback sans azure.functions
```

**`require_jwt` est additif** — ajouter en bas du fichier, ne rien modifier au-dessus.

### Pattern Key Vault à reproduire pour JWT_SECRET

```python
# Exactement le même pattern que _load_api_key()
_jwt_secret: Optional[str] = None

def _load_jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is not None:
        return _jwt_secret

    key_vault_url = os.environ.get("KEY_VAULT_URL")
    if key_vault_url:
        try:
            from shared.keyvault import KeyVaultClient
            kv = KeyVaultClient(vault_url=key_vault_url)
            value = kv.get_secret("JWT_SECRET")  # ← clé KV = "JWT_SECRET"
            if value:
                _jwt_secret = value
                return _jwt_secret
        except Exception as exc:
            logger.warning("Could not load JWT secret from Key Vault: %s", exc)

    value = os.environ.get("JWT_SECRET", "")
    if not value:
        raise EnvironmentError("JWT secret not configured (Key Vault: JWT_SECRET or env: JWT_SECRET)")

    _jwt_secret = value
    return _jwt_secret

def reset_jwt_secret() -> None:
    """Clear cached secret — used in tests."""
    global _jwt_secret
    _jwt_secret = None
```

### Implémentation `require_jwt`

```python
import jwt  # PyJWT

def require_jwt(handler: Callable) -> Callable:
    """
    Decorator that enforces JWT authentication on HTTP trigger handlers.

    Clients must send:  Authorization: Bearer <jwt_token>

    If valid, calls handler(req, user={"user_id": ..., "email": ...})
    """
    @functools.wraps(handler)
    def wrapper(req: Any) -> Any:
        request_id = str(uuid.uuid4())

        auth_header = ""
        if hasattr(req, "headers"):
            auth_header = req.headers.get("Authorization", "")

        if not auth_header:
            return _make_401("Missing Authorization header", request_id)

        if not auth_header.startswith("Bearer "):
            return _make_401("Invalid Authorization header format", request_id)

        token = auth_header.split(" ", 1)[1]

        try:
            secret = _load_jwt_secret()
        except EnvironmentError as exc:
            logger.error("JWT config error [%s]: %s", request_id, exc)
            return _make_401("Authentication service misconfigured", request_id)

        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return _make_401("Token has expired", request_id)
        except jwt.InvalidTokenError:
            return _make_401("Invalid token", request_id)

        user = {"user_id": payload.get("user_id"), "email": payload.get("email")}
        return handler(req, user=user)

    return wrapper
```

### PyJWT 2.x API — différences importantes vs 1.x

```python
# Encode (pour les tests — génère un vrai token)
import jwt, datetime
token = jwt.encode(
    {"user_id": 1, "email": "test@test.com", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)},
    "my-secret",
    algorithm="HS256"
)
# PyJWT 2.x → token est une str (pas bytes comme en 1.x)

# Decode
payload = jwt.decode(token, "my-secret", algorithms=["HS256"])
# Exceptions : jwt.ExpiredSignatureError, jwt.InvalidTokenError
```

### Pattern des tests (modèle : `test_auth.py`)

```python
# tests/test_jwt_middleware.py
import jwt, datetime, json
from unittest.mock import patch
import pytest
from shared.api.auth import require_jwt, reset_jwt_secret

JWT_SECRET = "test-jwt-secret"

def _make_token(payload: dict, secret=JWT_SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")

def _valid_payload(offset_hours=24) -> dict:
    return {
        "user_id": 42,
        "email": "user@test.com",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=offset_hours),
    }

class MockRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}

@pytest.fixture(autouse=True)
def clear_jwt_cache():
    reset_jwt_secret()
    yield
    reset_jwt_secret()
```

**Handler test avec `user` kwarg :**
```python
def make_handler():
    calls = []
    def handler(req, user=None):
        calls.append({"req": req, "user": user})
        return {"status_code": 200}
    return handler, calls
```

### `_make_401` réutilisé tel quel

La fonction `_make_401(message, request_id)` existante renvoie un `func.HttpResponse` (prod) ou `_Response` (tests). Elle est déjà dans le fichier — **pas besoin de la dupliquer**.

### Coexistence avec `require_auth`

| Décorateur | Vérifie | Utilisé par |
|---|---|---|
| `@require_auth` | `X-Api-Key` header | Endpoints production existants (`/v1/production/*`) |
| `@require_jwt` | `Authorization: Bearer` | Nouveaux endpoints (`/v1/auth/*`, `/v1/subscriptions`) |

Les deux coexistent dans `auth.py`. Aucun endpoint existant n'est modifié.

### Project Structure Notes

- Seul `functions/shared/api/auth.py` est modifié (ajout en bas)
- Nouveau fichier `tests/test_jwt_middleware.py` (distinct de `test_auth.py` qui couvre API Key)
- `pyproject.toml` et `requirements.txt` mis à jour (PyJWT)
- Naming : `reset_jwt_secret()` cohérent avec `reset_api_key()`

### References

- [Source: functions/shared/api/auth.py] — pattern `_load_api_key`, `require_auth`, `_make_401`, `_Response`
- [Source: functions/shared/keyvault.py] — `KeyVaultClient.get_secret(name, env_fallback)`
- [Source: tests/test_auth.py] — pattern de tests `MockRequest`, `MockHandler`, `autouse fixture`
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security] — PyJWT HS256, 24h, coexistence API Key
- [Source: _bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 2.1] — ACs

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- PyJWT 2.11.0 déjà présent dans le venv — ajouté à pyproject.toml et requirements.txt pour traçabilité
- `require_jwt` ajouté en bas de `auth.py` (additif — `require_auth` intact)
- `_load_jwt_secret()` + `reset_jwt_secret()` suivent exactement le pattern de `_load_api_key()`
- 16 tests dans `test_jwt_middleware.py` : valide (user_id, email, response), expiré, absent, malformé, non-Bearer, vide, mauvais secret, secret manquant, cache reset
- 285/285 tests passent, 0 régression
- Secret de test ≥ 32 bytes pour éviter `InsecureKeyLengthWarning` PyJWT 2.11
- Code review : `WWW-Authenticate: Bearer` corrigé (était `ApiKey`) ; `_make_401` paramétrisée ; `import jwt` déplacé au niveau module ; test `test_401_has_bearer_www_authenticate_header` ajouté

### File List

- `functions/shared/api/auth.py`
- `tests/test_jwt_middleware.py`
- `pyproject.toml`
- `requirements.txt`
