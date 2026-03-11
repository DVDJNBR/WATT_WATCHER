"""
RGPD Service — Story 6.1

Daily cleanup: warns accounts inactive for ≥ 11 months (one-time warning),
then deletes accounts inactive for ≥ 12 months (CASCADE FK cleans subscriptions and logs).

Called by the rgpd_cleanup_timer Azure Function in function_app.py.
"""

import calendar
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _subtract_months(dt: datetime, months: int) -> datetime:
    """
    Subtract N calendar months from a datetime, clamping to valid end-of-month day.

    Example: 2026-03-31 - 1 month = 2026-02-28 (not Feb 31).
    """
    m = dt.month - months
    y = dt.year + m // 12
    m = m % 12
    if m <= 0:
        m += 12
        y -= 1
    max_day = calendar.monthrange(y, m)[1]
    return dt.replace(year=y, month=m, day=min(dt.day, max_day))


def run_rgpd_cleanup(conn: Any, email_svc: Any) -> dict:
    """
    Run one daily RGPD cleanup cycle.

    Order:
      1. Delete accounts inactive ≥ 12 months (CASCADE cleans related rows).
      2. Warn accounts inactive ≥ 11 months (but < 12 months) with no prior warning.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        email_svc: EmailService instance (real or mock).

    Returns:
        {"warned": int, "deleted": int, "errors": int}
    """
    now = datetime.now(timezone.utc)
    threshold_11m = _subtract_months(now, 11).strftime("%Y-%m-%d")
    threshold_12m = _subtract_months(now, 12).strftime("%Y-%m-%d")

    warned = 0
    deleted = 0
    errors = 0
    cursor = conn.cursor()

    # ── Step 1: Delete accounts inactive ≥ 12 months ─────────────────────────
    cursor.execute(
        "SELECT id, email, last_activity FROM USER_ACCOUNT WHERE last_activity <= ?",
        (threshold_12m,),
    )
    to_delete = cursor.fetchall()

    for user_id, email, last_activity in to_delete:
        cursor.execute("DELETE FROM USER_ACCOUNT WHERE id = ?", (user_id,))
        conn.commit()
        logger.info(
            "RGPDCleanup: deleted user_id=%d email=%s last_activity=%s",
            user_id, email, last_activity,
        )
        deleted += 1

    # ── Step 2: Warn accounts inactive ≥ 11 months (< 12 months, no warning yet) ──
    cursor.execute(
        "SELECT id, email FROM USER_ACCOUNT "
        "WHERE last_activity <= ? AND last_activity > ? "
        "AND inactivity_warning_sent_at IS NULL",
        (threshold_11m, threshold_12m),
    )
    to_warn = cursor.fetchall()

    for user_id, email in to_warn:
        try:
            email_svc.send_inactivity_warning(email)
        except Exception as exc:
            logger.error(
                "RGPDCleanup: warning email failed user_id=%d email=%s: %s",
                user_id, email, exc,
            )
            errors += 1
            continue

        try:
            cursor.execute(
                "UPDATE USER_ACCOUNT SET inactivity_warning_sent_at = ? WHERE id = ?",
                (now, user_id),
            )
            conn.commit()
        except Exception as db_exc:
            logger.warning(
                "RGPDCleanup: failed to set inactivity_warning_sent_at user_id=%d: %s",
                user_id, db_exc,
            )
            warned += 1
            continue

        logger.info(
            "RGPDCleanup: warned user_id=%d email=%s",
            user_id, email,
        )
        warned += 1

    logger.info(
        "RGPDCleanup: cycle done warned=%d deleted=%d errors=%d",
        warned, deleted, errors,
    )
    return {"warned": warned, "deleted": deleted, "errors": errors}
