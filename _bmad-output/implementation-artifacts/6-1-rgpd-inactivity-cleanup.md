# Story 6.1: RGPD Inactivity Cleanup

Status: done

## Story

As a system,
I want inactive accounts to be automatically deleted after 12 months with a 30-day warning email,
so that RGPD compliance is maintained automatically without manual intervention.

## Acceptance Criteria

1. `last_activity` is updated on **every login** (already done in `auth_service.py:319`) and on **every subscription update** (`update_subscriptions` in `subscription_service.py` — missing, must be added)
2. A **daily timer function** detects accounts inactive for ≥ 11 months but < 12 months **and no warning already sent** → sends a warning email, records `inactivity_warning_sent_at`
3. The same timer detects accounts inactive for ≥ 12 months → deletes the account (CASCADE FK cleans up ALERT_SUBSCRIPTION + ALERT_SENT_LOG automatically)
4. Each deletion is logged (user_id, email, last_activity)
5. The cleanup logic is extracted to `functions/shared/alerting/rgpd_service.py` (testability — same pattern as `alert_dispatcher.py`)
6. Unit tests cover: warning sent, warning dedup (already warned), deletion, no-op (recent activity), both warning and deletion in one cycle

## Tasks / Subtasks

- [x] Migration `005_add_inactivity_warning_sent.sql` (AC: 2)
  - [x] `ALTER TABLE USER_ACCOUNT ADD inactivity_warning_sent_at DATETIME2 NULL` — idempotent `IF NOT EXISTS`
  - [x] SQLite equivalent for tests: add column to in-memory schema

- [x] Update `last_activity` on subscription update (AC: 1)
  - [x] In `subscription_service.update_subscriptions()`: add `UPDATE USER_ACCOUNT SET last_activity = ? WHERE id = ?` before `conn.commit()`
  - [x] Use `datetime.now(timezone.utc)` — same pattern as `auth_service.login()`

- [x] Add `send_inactivity_warning(to_email)` to `EmailService` (AC: 2)
  - [x] Subject: `[WATT WATCHER] Votre compte sera supprimé dans 30 jours`
  - [x] Body: explain inactivity, invite to log in to prevent deletion
  - [x] Mock mode: log only (same pattern as `send_alert`)

- [x] Create `functions/shared/alerting/rgpd_service.py` (AC: 2, 3, 4, 5)
  - [x] Function `run_rgpd_cleanup(conn, email_svc) -> dict`
  - [x] Compute `threshold_11m` and `threshold_12m` using Python month arithmetic (no dateutil)
  - [x] Query accounts for deletion: `SELECT id, email FROM USER_ACCOUNT WHERE last_activity <= ?` (threshold_12m)
  - [x] DELETE each → log `rgpd_deleted user_id=X email=Y last_activity=Z`
  - [x] Query accounts for warning: `last_activity <= threshold_11m AND last_activity > threshold_12m AND inactivity_warning_sent_at IS NULL`
  - [x] For each: `send_inactivity_warning(email)` → UPDATE `inactivity_warning_sent_at = now`
  - [x] Return `{"warned": int, "deleted": int, "errors": int}`

- [x] Add `rgpd_cleanup_timer` to `function_app.py` (AC: 2, 3)
  - [x] `@app.timer_trigger(schedule="0 0 0 * * *", arg_name="timer", run_on_startup=False)` — daily at midnight UTC
  - [x] Import `run_rgpd_cleanup`
  - [x] Same try/finally pattern as `alert_dispatch_timer`

- [x] Write tests `tests/test_rgpd_service.py` (AC: 6)
  - [x] `test_account_deleted_after_12_months` — user inactive 13 months → deleted
  - [x] `test_warning_sent_at_11_months` — user inactive 11.5 months → warning sent, `inactivity_warning_sent_at` set
  - [x] `test_warning_not_resent_if_already_warned` — warning already sent → skip
  - [x] `test_recent_user_not_affected` — last_activity = today → no action
  - [x] `test_deletion_cascades_subscriptions` — verify ALERT_SUBSCRIPTION deleted too
  - [x] `test_both_warning_and_deletion_in_one_cycle` — mix of users at different inactivity levels
  - [x] `test_return_counters_correct` — verify returned dict

## Dev Notes

### Pattern: same as `alert_dispatcher.py`

Logic extracted to `functions/shared/alerting/rgpd_service.py`. Timer in `function_app.py` is a thin wrapper (same pattern as `alert_dispatch_timer`):

```python
@app.timer_trigger(schedule="0 0 0 * * *", arg_name="timer", run_on_startup=False)
def rgpd_cleanup_timer(timer: func.TimerRequest) -> None:
    """Daily RGPD cleanup: warn inactive accounts (11 months) and delete (12 months)."""
    job_id = str(uuid.uuid4())
    logger.info("[%s] RGPD cleanup starting", job_id)
    conn = None
    try:
        conn = _get_db_connection()
        svc = EmailService()
        result = run_rgpd_cleanup(conn, svc)
        logger.info(
            "[%s] RGPD cleanup done: warned=%d deleted=%d errors=%d",
            job_id, result["warned"], result["deleted"], result["errors"],
        )
    except Exception as exc:
        logger.error("[%s] RGPD cleanup failed: %s", job_id, exc, exc_info=True)
    finally:
        if conn:
            conn.close()
```

### Month arithmetic (no dateutil)

`dateutil` is NOT in `requirements.txt` — do NOT add it. Use Python's `calendar` module:

```python
import calendar
from datetime import datetime, timezone

def _subtract_months(dt: datetime, months: int) -> datetime:
    """Subtract N calendar months from a datetime, clamping to valid day."""
    m = dt.month - months
    y = dt.year + m // 12
    m = m % 12
    if m <= 0:
        m += 12
        y -= 1
    max_day = calendar.monthrange(y, m)[1]
    return dt.replace(year=y, month=m, day=min(dt.day, max_day))
```

Usage in `run_rgpd_cleanup`:
```python
now = datetime.now(timezone.utc)
threshold_11m = _subtract_months(now, 11).strftime("%Y-%m-%d")
threshold_12m = _subtract_months(now, 12).strftime("%Y-%m-%d")
```

String format `"%Y-%m-%d"` works for both SQLite (`DATETIME TEXT`) and SQL Server (`DATETIME2`) — same approach validated in `alert_dispatcher.py`.

### `last_activity` update in `update_subscriptions`

Add before `conn.commit()` in `subscription_service.py`:

```python
from datetime import datetime, timezone

# ... inside update_subscriptions, after inserting all rows, before conn.commit():
cursor.execute(
    "UPDATE USER_ACCOUNT SET last_activity = ? WHERE id = ?",
    (datetime.now(timezone.utc), user_id),
)
conn.commit()
```

Pattern identical to `auth_service.login()` (line 318-322).

### Deletion order: delete 12-month accounts FIRST

Process deletions before warnings in `run_rgpd_cleanup` to avoid warning an account that is about to be deleted (edge case where 11-month and 12-month thresholds overlap on the same day for the same user — shouldn't happen but defensive).

### Warning dedup logic

`inactivity_warning_sent_at IS NULL` filter ensures warning is sent only once.
If the user logs in after receiving the warning, `last_activity` is updated → they exit the 11-month window → `inactivity_warning_sent_at` remains set but becomes irrelevant (their account won't be deleted).
If they become inactive again later, `inactivity_warning_sent_at` remains set from the previous cycle. To re-warn, we'd need to reset it — but per ACs, this is out of scope.

### Test schema (SQLite in-memory)

Tests use `sqlite3.connect(":memory:")`. Schema needs:

```sql
CREATE TABLE USER_ACCOUNT (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    is_confirmed INTEGER NOT NULL DEFAULT 1,
    last_activity TEXT NOT NULL,
    inactivity_warning_sent_at TEXT NULL
);
CREATE TABLE ALERT_SUBSCRIPTION (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES USER_ACCOUNT(id)
);
```

For cascade DELETE in SQLite, enable foreign keys: `conn.execute("PRAGMA foreign_keys = ON")`.

### Cron schedule

`"0 0 0 * * *"` = Azure Functions format: `{second} {minute} {hour} {day} {month} {day-of-week}` → every day at 00:00:00 UTC.

### Migration 005

```sql
-- Migration 005: Add inactivity_warning_sent_at to USER_ACCOUNT
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'USER_ACCOUNT'
      AND COLUMN_NAME = 'inactivity_warning_sent_at'
)
    ALTER TABLE USER_ACCOUNT
    ADD inactivity_warning_sent_at DATETIME2 NULL;
```

### References

- `functions/shared/alerting/alert_dispatcher.py` — pattern thin service + timer to reproduce exactly
- `functions/shared/api/auth_service.py:318-322` — `last_activity` update pattern
- `functions/shared/api/subscription_service.py:82-98` — where to add `last_activity` update
- `functions/shared/api/email_service.py` — add `send_inactivity_warning()` alongside `send_confirmation/send_reset/send_alert`
- `functions/migrations/004_add_confirmation_token_expires.sql` — idempotent ALTER TABLE pattern
- `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` — cascade FK, RGPD requirements
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 6.1` — ACs source

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### Completion Notes List

- `_subtract_months()` helper in `rgpd_service.py` uses `calendar.monthrange` for correct end-of-month clamping (no dateutil dependency)
- Deletion processed before warning to avoid warning an account about to be deleted
- `inactivity_warning_sent_at IS NULL` filter ensures one-time warning per inactivity cycle
- `last_activity` now updated on subscription update (was missing, already done for login)
- 433/433 tests passing, 0 regressions

### File List

- `functions/migrations/005_add_inactivity_warning_sent.sql` — new: idempotent ALTER TABLE for `inactivity_warning_sent_at`
- `functions/shared/api/subscription_service.py` — modified: `last_activity` update in `update_subscriptions()`
- `functions/shared/api/email_service.py` — modified: added `send_inactivity_warning(to_email)`
- `functions/shared/alerting/rgpd_service.py` — new: `run_rgpd_cleanup(conn, email_svc) -> dict`
- `functions/function_app.py` — modified: import `run_rgpd_cleanup`, added `rgpd_cleanup_timer` daily timer
- `tests/test_rgpd_service.py` — new: 8 unit tests covering all ACs
