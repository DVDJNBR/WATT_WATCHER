"""
Alert Dispatcher — Story 5.3

Orchestrates hourly alert detection, subscriber lookup, deduplication,
and email sending via EmailService.

Called by the alert_dispatch_timer Azure Function in function_app.py.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from shared.alerting.alert_detector import detect

logger = logging.getLogger(__name__)


def dispatch_alerts(conn: Any, email_svc: Any) -> dict:
    """
    Run one dispatch cycle: detect → match subscribers → dedup → send.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        email_svc: EmailService instance (real or mock).

    Returns:
        {"detected": int, "sent": int, "skipped_dedup": int, "errors": int}
    """
    alerts = detect(conn)
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sent = 0
    skipped = 0
    errors = 0
    cursor = conn.cursor()

    for alert in alerts:
        region_code = alert["region_code"]
        alert_type = alert["alert_type"]
        prod_mw = alert["prod_mw"]
        conso_mw = alert["conso_mw"]

        # Find active subscribers for this region + alert_type
        cursor.execute(
            "SELECT u.id, u.email "
            "FROM ALERT_SUBSCRIPTION s "
            "JOIN USER_ACCOUNT u ON s.user_id = u.id "
            "WHERE s.region_code = ? AND s.alert_type = ? AND s.is_active = 1",
            (region_code, alert_type),
        )
        subscribers = cursor.fetchall()

        for user_id, email in subscribers:
            # Dedup: skip if already sent today
            cursor.execute(
                "SELECT 1 FROM ALERT_SENT_LOG "
                "WHERE user_id = ? AND region_code = ? AND alert_type = ? AND sent_at >= ?",
                (user_id, region_code, alert_type, today_start),
            )
            if cursor.fetchone():
                logger.info(
                    "AlertDispatcher: skip dedup user=%d region=%s type=%s",
                    user_id, region_code, alert_type,
                )
                skipped += 1
                continue

            # Send email
            try:
                email_svc.send_alert(email, region_code, alert_type, prod_mw, conso_mw)
            except Exception as exc:
                logger.error(
                    "AlertDispatcher: email failed user=%d region=%s type=%s: %s",
                    user_id, region_code, alert_type, exc,
                )
                errors += 1
                continue  # Don't insert log — retry next cycle

            # Log successful send
            try:
                cursor.execute(
                    "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type) VALUES (?, ?, ?)",
                    (user_id, region_code, alert_type),
                )
                conn.commit()
            except Exception as db_exc:
                # Concurrent timer fired simultaneously — UNIQUE INDEX rejected duplicate.
                # Email was sent once; treat as success (dedup will catch next cycle).
                logger.warning(
                    "AlertDispatcher: log insert skipped (concurrent dedup?) user=%d region=%s type=%s: %s",
                    user_id, region_code, alert_type, db_exc,
                )
                sent += 1
                continue
            logger.info(
                "AlertDispatcher: sent user=%d region=%s type=%s",
                user_id, region_code, alert_type,
            )
            sent += 1

    logger.info(
        "AlertDispatcher: cycle done detected=%d sent=%d skipped=%d errors=%d",
        len(alerts), sent, skipped, errors,
    )
    return {"detected": len(alerts), "sent": sent, "skipped_dedup": skipped, "errors": errors}
