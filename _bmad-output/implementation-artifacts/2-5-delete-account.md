# Story 2.5: Delete Account Endpoint

Status: done

## Story

As a connected user,
I want to delete my account permanently,
so that my data is removed (RGPD).

## Acceptance Criteria

1. `DELETE /v1/auth/account` est protégé par `@require_jwt` — retourne 401 sans token valide
2. Supprime la ligne `USER_ACCOUNT` correspondant au `user_id` extrait du JWT
3. La suppression cascade sur `ALERT_SUBSCRIPTION` et `ALERT_SENT_LOG` (contraintes FK `ON DELETE CASCADE`)
4. Retourne 204 No Content (pas de body)
5. Test : vérifier que les tables liées sont bien vidées après suppression

## Tasks / Subtasks

- [x] Ajouter route dans `functions/shared/api/routes.py` (AC: 1)
  - [x] `ROUTE_AUTH_ACCOUNT = "v1/auth/account"`
- [x] Implémenter `delete_account()` dans `functions/shared/api/auth_service.py` (AC: 2, 3)
  - [x] `delete_account(conn, user_id: int) -> None`
  - [x] `DELETE FROM USER_ACCOUNT WHERE id = ?` — la cascade FK gère ALERT_SUBSCRIPTION et ALERT_SENT_LOG
  - [x] `conn.commit()`
- [x] Ajouter l'endpoint dans `functions/function_app.py` (AC: 1, 2, 4)
  - [x] `DELETE /v1/auth/account` → `@require_jwt` → 204 No Content
  - [x] Handler signature : `def delete_auth_account(req, user)` (user injecté par `@require_jwt`)
  - [x] Retourner `func.HttpResponse(body="", status_code=204, headers={"X-Request-Id": request_id})`
  - [x] Pattern `conn = None` + `finally: conn.close()`
- [x] Écrire les tests dans `tests/test_delete_account.py` (AC: 2, 3, 5)
  - [x] `delete_account` supprime la ligne USER_ACCOUNT
  - [x] `delete_account` cascade → ALERT_SUBSCRIPTION vidée
  - [x] `delete_account` cascade → ALERT_SENT_LOG vidée
  - [x] `delete_account` user_id inexistant → pas d'exception (idempotent)

## Dev Notes

### Contexte : ce qui existe déjà

**`functions/shared/api/auth.py`** contient :
- `require_jwt` — décorateur JWT, signature handler : `def handler(req, user={"user_id": ..., "email": ...})`
- `_make_401()` — retourne 401 si token absent/invalide/expiré — **testé dans `tests/test_jwt_middleware.py`**
- `reset_jwt_secret()` — pour les tests

**`functions/shared/api/auth_service.py`** contient déjà toute la logique auth. `delete_account()` sera la fonction la plus simple de ce fichier : une seule requête SQL DELETE.

**`functions/function_app.py`** — patterns établis :
```python
@app.route(route=ROUTE_AUTH_ACCOUNT, methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
@require_jwt
def delete_auth_account(req: func.HttpRequest, user: dict) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    conn = None
    try:
        conn = _get_db_connection()
        delete_account(conn, user["user_id"])
        return func.HttpResponse(
            body="", status_code=204,
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("delete-account error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()
```

### ⚠️ `@require_jwt` + `auth_level=ANONYMOUS`

`auth_level=func.AuthLevel.ANONYMOUS` signifie que Azure Functions ne vérifie **pas** la Function Key. L'auth JWT est gérée par le décorateur `@require_jwt`. C'est le même pattern que tous les autres endpoints auth.

### ⚠️ `@require_jwt` ordre de décoration

```python
@app.route(...)       # ← Azure SDK registration — DOIT être le premier décorateur
@require_jwt          # ← middleware custom — DOIT être après @app.route
def delete_auth_account(req, user):
    ...
```

Si l'ordre est inversé, Azure Functions ne reconnaîtra pas la fonction.

### Cascade FK — déjà en place

Les migrations 002 et 003 définissent :
```sql
user_id INT NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE
```

→ `DELETE FROM USER_ACCOUNT WHERE id = ?` supprime automatiquement les lignes liées dans `ALERT_SUBSCRIPTION` et `ALERT_SENT_LOG`. Pas besoin de DELETE explicites sur ces tables.

### Idempotence

Si `user_id` n'existe plus en BDD (suppression déjà effectuée, ou token JWT d'un compte précédemment supprimé), le DELETE n'affecte aucune ligne mais ne lève pas d'exception. Comportement correct — idempotent.

### 204 No Content dans Azure Functions

```python
return func.HttpResponse(
    body="",
    status_code=204,
    headers={"X-Request-Id": request_id},
)
```

Ne pas inclure `mimetype` (body vide). `func.HttpResponse` accepte `body=""` pour 204.

### Pattern des tests (tests/test_delete_account.py)

```python
"""Tests for Story 2.5 — Delete Account."""
import sqlite3
import pytest
from shared.api.auth_service import delete_account, register, confirm_email, login

def _make_db():
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
    conn.execute("""
        CREATE TABLE ALERT_SUBSCRIPTION (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER  NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT     NOT NULL,
            alert_type  TEXT     NOT NULL,
            is_active   INTEGER  NOT NULL DEFAULT 1,
            created_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ALERT_SENT_LOG (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER  NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT     NOT NULL,
            alert_type  TEXT     NOT NULL,
            sent_at     TEXT
        )
    """)
    # Enable FK enforcement in SQLite (off by default)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

**⚠️ PRAGMA foreign_keys = ON** : SQLite ne respecte pas les contraintes FK par défaut. Il faut activer `PRAGMA foreign_keys = ON` sur chaque connexion pour que le cascade DELETE fonctionne dans les tests.

**⚠️ SQLite FK cascade** : Le cascade fonctionne dans SQLite uniquement si `foreign_keys` est activé ET que les tables liées sont créées avec `REFERENCES ... ON DELETE CASCADE`. Ne pas oublier cette pragma dans `_make_db()`.

### Implémentation de `delete_account()`

```python
def delete_account(conn: Any, user_id: int) -> None:
    """
    Permanently delete a user account and all associated data.

    The ON DELETE CASCADE constraints on ALERT_SUBSCRIPTION and ALERT_SENT_LOG
    handle cleanup of linked rows automatically.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        user_id: ID of the account to delete.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM USER_ACCOUNT WHERE id = ?", (user_id,))
    conn.commit()
```

### References

- `functions/shared/api/auth.py` — `require_jwt`, signature `handler(req, user=dict)`, `reset_jwt_secret()`
- `functions/shared/api/auth_service.py` — pattern `conn.cursor()` + `conn.commit()`
- `functions/function_app.py` — pattern `conn = None` + `finally: conn.close()`, ordre `@app.route` avant `@require_jwt`
- `functions/shared/api/routes.py` — pattern `ROUTE_AUTH_*`
- `functions/migrations/002_create_alert_subscription.sql` — `ON DELETE CASCADE` confirmé
- `functions/migrations/003_create_alert_sent_log.sql` — `ON DELETE CASCADE` confirmé
- `tests/test_jwt_middleware.py` — les tests 401 du décorateur `@require_jwt` sont déjà couverts → ne pas dupliquer
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 2.5` — ACs source
- `_bmad-output/planning-artifacts/architecture.md` — FK cascade DELETE, RGPD, `@require_jwt`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- `PRAGMA foreign_keys = ON` activé dans `_make_db()` — requis pour que le cascade DELETE fonctionne dans SQLite
- `delete_account()` = 2 lignes — la cascade FK (migrations 002+003) gère tout automatiquement
- 7 tests couvrent: suppression USER_ACCOUNT, cascade ALERT_SUBSCRIPTION, cascade ALERT_SENT_LOG, cascade multi-abonnements, isolation entre utilisateurs, idempotence (user inexistant + double suppression)
- Tests `@require_jwt` (401) déjà couverts dans `test_jwt_middleware.py` — non dupliqués
- 383/383 tests, 0 régression

### File List

- `functions/shared/api/routes.py`
- `functions/shared/api/auth_service.py`
- `functions/function_app.py`
- `tests/test_delete_account.py`
