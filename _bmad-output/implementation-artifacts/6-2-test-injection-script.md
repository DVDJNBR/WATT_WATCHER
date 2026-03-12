# Story 6.2: Test Injection Script

Status: done

## Story

As an admin,
I want a script to inject fake production/consumption data that triggers alerts,
so that I can validate the alert pipeline end-to-end without waiting for real RTE events.

## Acceptance Criteria

1. Script at `functions/scripts/inject_test_data.py`
2. **Inject mode**: inserts Gold data simulating `under_production` or `over_production` for a target region — data becomes the latest timestamp so `detect()` picks it up immediately
3. **Restore mode**: removes all injected data (DIM_TIME sentinel row + FACT_ENERGY_FLOW rows with source `TEST_INJECTION`) — leaves real data untouched
4. Script is self-documented (module-level docstring with usage examples)
5. Works locally (SQLite via `LOCAL_GOLD_DB` or default `gold.db`) and in Azure (via `SQL_CONNECTION_STRING` env var → pyodbc)
6. Exits with non-zero code on error

## Tasks / Subtasks

- [x] Create `functions/scripts/` directory and `__init__.py` (AC: 1)

- [x] Implement `inject_test_data.py` with inject + restore modes (AC: 1-6)
  - [x] Module-level docstring with usage examples (AC: 4)
  - [x] `argparse` CLI: `--mode {inject,restore}`, `--region CODE`, `--alert-type {under_production,over_production}`, `--prod-mw FLOAT`, `--conso-mw FLOAT`
  - [x] DB connection helper (same pattern as `function_app.py:_get_db_connection`) — `SQL_CONNECTION_STRING` → pyodbc, else sqlite3
  - [x] `inject(conn, region_code, alert_type, prod_mw, conso_mw)`: insert sentinel DIM_TIME, ensure DIM_REGION + TEST_INJECTION source exist, insert FACT_ENERGY_FLOW row (AC: 2)
  - [x] `restore(conn)`: delete FACT_ENERGY_FLOW rows for TEST_INJECTION source + sentinel DIM_TIME row (AC: 3)
  - [x] `main()`: parse args, call inject or restore, log result, `sys.exit(1)` on exception (AC: 5, 6)

- [x] Write tests `tests/test_inject_test_data.py` (AC: 2, 3)
  - [x] `test_inject_creates_fact_row` — after inject, FACT_ENERGY_FLOW has row with correct prod/conso
  - [x] `test_inject_under_production` — prod_mw < conso_mw → `detect()` returns `under_production` for region
  - [x] `test_inject_over_production` — prod_mw > conso_mw → `detect()` returns `over_production` for region
  - [x] `test_restore_removes_injected_data` — after inject+restore, FACT_ENERGY_FLOW is empty again
  - [x] `test_restore_idempotent` — calling restore twice does not raise
  - [x] `test_inject_does_not_affect_other_regions` — injection for FR does not create row for IDF

## Dev Notes

### Sentinel timestamp strategy

`alert_detector.detect()` uses `MAX(horodatage)` to select the latest data:
```sql
WHERE t.horodatage = (SELECT MAX(t2.horodatage) FROM FACT_ENERGY_FLOW f2 JOIN DIM_TIME t2 ON f2.id_date = t2.id_date)
```
By injecting with timestamp `"2099-12-31T23:59:00"` (clearly in the future), the injected rows will always be `MAX` and will always be picked by `detect()`. This timestamp is the single "injection marker" — restore just deletes this DIM_TIME row (CASCADE or explicit deletion of FACT_ENERGY_FLOW rows first).

### Source marker: `TEST_INJECTION`

All injected FACT_ENERGY_FLOW rows use DIM_SOURCE name `"TEST_INJECTION"`. Restore query:
```sql
DELETE FROM FACT_ENERGY_FLOW
WHERE id_source = (SELECT id_source FROM DIM_SOURCE WHERE source_name = 'TEST_INJECTION')
  AND id_date   = (SELECT id_date FROM DIM_TIME WHERE horodatage = '2099-12-31T23:59:00');

DELETE FROM DIM_TIME WHERE horodatage = '2099-12-31T23:59:00';
-- DIM_SOURCE 'TEST_INJECTION' is kept (harmless, idempotent)
```

DIM_REGION for the target region is kept — it's real data.

### Inject logic

```python
SENTINEL_TS = "2099-12-31T23:59:00"
TEST_SOURCE  = "TEST_INJECTION"

def inject(conn, region_code: str, alert_type: str, prod_mw: float, conso_mw: float) -> None:
    cursor = conn.cursor()
    # 1. Ensure DIM_TIME sentinel row
    cursor.execute("SELECT id_date FROM DIM_TIME WHERE horodatage = ?", (SENTINEL_TS,))
    row = cursor.fetchone()
    if row:
        id_date = row[0]
    else:
        cursor.execute("INSERT INTO DIM_TIME (horodatage) VALUES (?)", (SENTINEL_TS,))
        id_date = cursor.lastrowid  # sqlite3; pyodbc needs SELECT SCOPE_IDENTITY()

    # 2. Ensure DIM_REGION for region_code
    cursor.execute("SELECT id_region FROM DIM_REGION WHERE code_insee = ?", (region_code,))
    row = cursor.fetchone()
    if row:
        id_region = row[0]
    else:
        cursor.execute("INSERT INTO DIM_REGION (code_insee, nom_region) VALUES (?, ?)", (region_code, region_code))
        id_region = cursor.lastrowid

    # 3. Ensure DIM_SOURCE TEST_INJECTION
    cursor.execute("SELECT id_source FROM DIM_SOURCE WHERE source_name = ?", (TEST_SOURCE,))
    row = cursor.fetchone()
    if row:
        id_source = row[0]
    else:
        cursor.execute("INSERT INTO DIM_SOURCE (source_name) VALUES (?)", (TEST_SOURCE,))
        id_source = cursor.lastrowid

    # 4. Insert FACT_ENERGY_FLOW row
    cursor.execute(
        "INSERT INTO FACT_ENERGY_FLOW (id_region, id_date, id_source, valeur_mw, consommation_mw) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_region, id_date, id_source, prod_mw, conso_mw),
    )
    conn.commit()
```

### `cursor.lastrowid` vs pyodbc

`cursor.lastrowid` works in sqlite3. In pyodbc (SQL Server), use:
```python
cursor.execute("SELECT SCOPE_IDENTITY()")
id_val = int(cursor.fetchone()[0])
```
Detect which driver by checking `type(conn).__module__`:
```python
def _last_inserted_id(cursor, conn) -> int:
    if "sqlite3" in type(conn).__module__:
        return cursor.lastrowid
    cursor.execute("SELECT SCOPE_IDENTITY()")
    return int(cursor.fetchone()[0])
```

### DB connection (same pattern as function_app.py)

```python
import os, sys

def _get_connection():
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    if conn_str:
        import pyodbc
        return pyodbc.connect(conn_str, timeout=90)
    import sqlite3
    from pathlib import Path
    local_db = os.environ.get("LOCAL_GOLD_DB", str(Path(__file__).parent.parent.parent / "gold.db"))
    return sqlite3.connect(local_db)
```

### CLI usage (module docstring content)

```
Usage:
    Inject under_production for region FR:
        python inject_test_data.py --mode inject --region FR --alert-type under_production
        (defaults: --prod-mw 4000 --conso-mw 6000)

    Inject over_production for region FR:
        python inject_test_data.py --mode inject --region FR --alert-type over_production --prod-mw 8000 --conso-mw 5000

    Remove all injected data:
        python inject_test_data.py --mode restore

    In Azure: set SQL_CONNECTION_STRING env var, then call main() from an HTTP trigger or admin script.
```

### Test schema (SQLite in-memory)

Tests use sqlite3 in-memory with the same schema as `test_alert_detector.py`:
```python
CREATE TABLE DIM_REGION (id_region INTEGER PRIMARY KEY AUTOINCREMENT, code_insee TEXT NOT NULL, nom_region TEXT);
CREATE TABLE DIM_TIME   (id_date   INTEGER PRIMARY KEY AUTOINCREMENT, horodatage TEXT NOT NULL);
CREATE TABLE DIM_SOURCE (id_source INTEGER PRIMARY KEY AUTOINCREMENT, source_name TEXT NOT NULL);
CREATE TABLE FACT_ENERGY_FLOW (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_region INTEGER, id_date INTEGER, id_source INTEGER,
    valeur_mw REAL, consommation_mw REAL
);
```

Import `inject`, `restore` directly (not the CLI `main()`). Use `detect()` from `alert_detector.py` to validate end-to-end.

### References

- `functions/shared/alerting/alert_detector.py` — `detect(conn)` uses `MAX(horodatage)` subquery; injected data must become the new MAX
- `functions/shared/gold/dim_loader.py:284-303` — `get_region_id`, `get_time_id`, `get_source_id` helpers for understanding Gold table access patterns
- `functions/function_app.py:60-86` — `_get_db_connection()` pattern to reproduce in script
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 6.2` — ACs source
- `tests/test_alert_detector.py` — SQLite schema pattern to reuse in test_inject_test_data.py

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### Completion Notes List

- Sentinel timestamp `"2099-12-31T23:59:00"` guarantees inject data is always `MAX(horodatage)` → picked by `detect()`
- `_ensure_row()` helper makes inject fully idempotent for DIM_* tables
- `_last_inserted_id()` handles sqlite3 (`lastrowid`) vs pyodbc (`SCOPE_IDENTITY()`) compatibility
- Input validation raises `ValueError` if alert_type/values are inconsistent
- 455/455 tests passing, 0 regressions (19 tests in test_inject_test_data.py)
- CR M1 fix: `main()` tests use file-based SQLite + `side_effect=lambda: sqlite3.connect(db_path)` to avoid `sqlite3.ProgrammingError` from `conn.close()` in `finally`
- CR L1 fix: inject docstring corrected — "Not idempotent for FACT_ENERGY_FLOW"
- CR L2 fix: restore uses explicit `SELECT COUNT(*)` before DELETE instead of unreliable `cursor.rowcount`

### File List

- `functions/scripts/__init__.py` — new: scripts package
- `functions/scripts/inject_test_data.py` — new: inject/restore CLI with `argparse`, full docstring
- `tests/test_inject_test_data.py` — new: 15 tests (inject, restore, end-to-end with detect(), validation)
