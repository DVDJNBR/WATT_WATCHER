# Story 4.1: Subscriptions API

Status: done

## Story

As a connected user,
I want to manage my alert subscriptions via API,
so that my preferences are persisted.

## Acceptance Criteria

1. `GET /v1/subscriptions` retourne les abonnements actifs (`is_active=1`) de l'utilisateur connecté — protégé par `@require_jwt`
2. `PUT /v1/subscriptions` remplace la liste complète des abonnements (DELETE all + INSERT new) — protégé par `@require_jwt`
3. Format entrée/sortie : `[{ "region_code": str, "alert_type": str, "is_active": bool }]`
4. `alert_type` validé : doit être `"under_production"` ou `"over_production"`
5. Abonnement dupliqué (même `region_code` + `alert_type`) dans le payload PUT → 400

## Tasks / Subtasks

- [x] Créer `functions/shared/api/subscription_service.py` (AC: 1, 2, 3, 4, 5)
  - [x] `get_subscriptions(conn, user_id: int) -> list[dict]` — SELECT WHERE is_active=1
  - [x] `update_subscriptions(conn, user_id: int, subscriptions: list[dict]) -> list[dict]`
    - [x] Valider chaque item : `region_code` non-vide, `alert_type` dans VALID_ALERT_TYPES
    - [x] Valider pas de doublon `(region_code, alert_type)` dans le payload
    - [x] DELETE FROM ALERT_SUBSCRIPTION WHERE user_id = ?
    - [x] INSERT chaque subscription
    - [x] Retourner la liste insérée
- [x] Ajouter routes dans `functions/shared/api/routes.py` (AC: 1, 2)
  - [x] `ROUTE_SUBSCRIPTIONS = "v1/subscriptions"`
- [x] Ajouter 2 endpoints dans `functions/function_app.py` (AC: 1, 2)
  - [x] `GET /v1/subscriptions` → `@require_jwt` → 200 + liste
  - [x] `PUT /v1/subscriptions` → `@require_jwt` → 200 + liste mise à jour, ou 400
- [x] Écrire les tests dans `tests/test_subscriptions.py` (AC: 1, 2, 3, 4, 5)
  - [x] GET utilisateur sans abonnements → liste vide
  - [x] GET retourne seulement les abonnements actifs
  - [x] PUT liste vide → tous abonnements supprimés
  - [x] PUT insère les abonnements et les retourne
  - [x] PUT remplace la liste précédente (replace-all)
  - [x] PUT alert_type invalide → ValueError
  - [x] PUT doublon dans le payload → ValueError
  - [x] PUT region_code vide → ValueError
  - [x] GET après PUT retourne la liste mise à jour

## Dev Notes

### Schema ALERT_SUBSCRIPTION (migration 002)

```sql
CREATE TABLE ALERT_SUBSCRIPTION (
    id          INT             PRIMARY KEY IDENTITY(1,1),
    user_id     INT             NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
    region_code NVARCHAR(10)    NOT NULL,
    alert_type  NVARCHAR(50)    NOT NULL,  -- 'under_production' | 'over_production'
    is_active   BIT             NOT NULL DEFAULT 1,
    created_at  DATETIME2       NOT NULL DEFAULT GETUTCDATE()
)
```

SQLite test : `INTEGER` au lieu de `INT`, `TEXT` au lieu de `NVARCHAR`.

### Constante VALID_ALERT_TYPES

```python
VALID_ALERT_TYPES = {"under_production", "over_production"}
```

### Implémentation de `get_subscriptions()`

```python
def get_subscriptions(conn: Any, user_id: int) -> list:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT region_code, alert_type, is_active FROM ALERT_SUBSCRIPTION "
        "WHERE user_id = ? AND is_active = 1 ORDER BY region_code, alert_type",
        (user_id,),
    )
    rows = cursor.fetchall()
    return [
        {"region_code": r[0], "alert_type": r[1], "is_active": bool(r[2])}
        for r in rows
    ]
```

### Implémentation de `update_subscriptions()`

```python
VALID_ALERT_TYPES = {"under_production", "over_production"}

def update_subscriptions(conn: Any, user_id: int, subscriptions: list) -> list:
    """
    Replace all subscriptions for a user.

    Raises:
        ValueError: invalid alert_type, empty region_code, or duplicate (region_code, alert_type).
    """
    # Validation
    seen = set()
    for sub in subscriptions:
        region_code = (sub.get("region_code") or "").strip()
        alert_type = sub.get("alert_type", "")
        if not region_code:
            raise ValueError("region_code cannot be empty")
        if alert_type not in VALID_ALERT_TYPES:
            raise ValueError(
                f"Invalid alert_type '{alert_type}'. Must be one of: {sorted(VALID_ALERT_TYPES)}"
            )
        key = (region_code, alert_type)
        if key in seen:
            raise ValueError(
                f"Duplicate subscription: region_code='{region_code}', alert_type='{alert_type}'"
            )
        seen.add(key)

    cursor = conn.cursor()
    # Replace-all: delete then insert
    cursor.execute("DELETE FROM ALERT_SUBSCRIPTION WHERE user_id = ?", (user_id,))
    result = []
    for sub in subscriptions:
        region_code = sub["region_code"].strip()
        alert_type = sub["alert_type"]
        is_active = bool(sub.get("is_active", True))
        cursor.execute(
            "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) "
            "VALUES (?, ?, ?, ?)",
            (user_id, region_code, alert_type, 1 if is_active else 0),
        )
        result.append({
            "region_code": region_code,
            "alert_type": alert_type,
            "is_active": is_active,
        })
    conn.commit()
    return result
```

### Endpoints dans function_app.py

**Imports à ajouter :**
```python
from shared.api.routes import (..., ROUTE_SUBSCRIPTIONS)
from shared.api.subscription_service import get_subscriptions, update_subscriptions
```

**GET** :
```python
@app.route(route=ROUTE_SUBSCRIPTIONS, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@require_jwt
def get_subscriptions_endpoint(req: func.HttpRequest, user: dict) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    user_id = user.get("user_id")
    if not user_id:
        return func.HttpResponse(
            json.dumps(bad_request("Invalid token claims", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    conn = None
    try:
        conn = _get_db_connection()
        result = get_subscriptions(conn, user_id)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "subscriptions": result}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("get-subscriptions error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()
```

**PUT** :
```python
@app.route(route=ROUTE_SUBSCRIPTIONS, methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
@require_jwt
def put_subscriptions_endpoint(req: func.HttpRequest, user: dict) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    user_id = user.get("user_id")
    if not user_id:
        return func.HttpResponse(
            json.dumps(bad_request("Invalid token claims", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    try:
        body = req.get_json()
    except Exception:
        body = []
    if not isinstance(body, list):
        return func.HttpResponse(
            json.dumps(bad_request("Body must be a JSON array", request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    conn = None
    try:
        conn = _get_db_connection()
        result = update_subscriptions(conn, user_id, body)
        return func.HttpResponse(
            json.dumps({"request_id": request_id, "subscriptions": result}),
            status_code=200, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except ValueError as exc:
        return func.HttpResponse(
            json.dumps(bad_request(str(exc), request_id)),
            status_code=400, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        logger.error("put-subscriptions error [%s]: %s", request_id, exc, exc_info=True)
        return func.HttpResponse(
            json.dumps(server_error(request_id=request_id)),
            status_code=500, mimetype="application/json",
            headers={"X-Request-Id": request_id},
        )
    finally:
        if conn:
            conn.close()
```

### Pattern des tests (tests/test_subscriptions.py)

```python
def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmation_token TEXT, confirmation_token_expires TEXT,
            reset_token TEXT, reset_token_expires TEXT,
            last_activity TEXT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ALERT_SUBSCRIPTION (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.execute("INSERT INTO USER_ACCOUNT (id, email, password_hash) VALUES (1, 'u@t.com', 'h')")
    conn.commit()
    return conn
```

Note : pour les tests subscription, pas besoin de passer par `register()` / `confirm_email()`. Insérer directement un USER_ACCOUNT minimal suffit.

### ⚠️ Deux routes GET + PUT sur le même path

Azure Functions supporte plusieurs méthodes sur le même `route` — définir deux handlers distincts avec `methods=["GET"]` et `methods=["PUT"]` respectivement. C'est le pattern standard.

### ⚠️ `is_active` en SQLite vs Azure SQL

SQLite stocke `BIT` comme `INTEGER` (0/1). `bool(r[2])` convertit correctement `0→False` et `1→True`. Pyodbc retourne également `True/False` pour les colonnes `BIT` en Azure SQL.

### References

- `functions/shared/api/auth.py` — `require_jwt`, pattern `user.get("user_id")`
- `functions/function_app.py` — pattern `@app.route` + `@require_jwt`, `conn = None` + finally
- `functions/shared/api/routes.py` — pattern `ROUTE_*`
- `functions/migrations/002_create_alert_subscription.sql` — schema ALERT_SUBSCRIPTION
- `tests/test_delete_account.py` — pattern `_make_db()` avec PRAGMA foreign_keys + ALERT_SUBSCRIPTION
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 4.1` — ACs source

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

N/A — all 13 tests passed on first run.

### Completion Notes List

- `test_put_validation_error_does_not_delete_existing` added beyond story spec to verify atomicity (validate-all before any DB write).
- Pre-existing test collection errors (Python 3.8 vs 3.10+ syntax, bcrypt cffi) are not related to this story.

### Code Review Fixes (CR)

- **H1 fixed**: Malformed JSON in PUT body now returns 400 instead of silently falling back to `[]` (which would have triggered a DELETE ALL). (`function_app.py`)
- **M1 fixed**: Removed unused `import logging` / `logger` from `subscription_service.py`.

### File List

- `functions/shared/api/subscription_service.py` (new)
- `functions/shared/api/routes.py` (ROUTE_SUBSCRIPTIONS added)
- `functions/function_app.py` (imports + 2 endpoints added)
- `tests/test_subscriptions.py` (new, 13 tests)
