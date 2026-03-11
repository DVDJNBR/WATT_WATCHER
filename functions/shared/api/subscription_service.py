"""
Subscription Service — Story 4.1

Handles GET and PUT /v1/subscriptions.
Users manage their alert subscriptions (region_code + alert_type pairs).
PUT is a replace-all operation: deletes existing then inserts new.

DB compatibility: works with both pyodbc (Azure SQL) and sqlite3 (local/tests).
Both use '?' as placeholder.
"""

from datetime import datetime, timezone
from typing import Any

VALID_ALERT_TYPES = {"under_production", "over_production"}


def get_subscriptions(conn: Any, user_id: int) -> list:
    """
    Return active subscriptions for a user.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        user_id: Authenticated user ID from JWT.

    Returns:
        List of dicts: [{"region_code": str, "alert_type": str, "is_active": bool}]
    """
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


def update_subscriptions(conn: Any, user_id: int, subscriptions: list) -> list:
    """
    Replace all subscriptions for a user (delete-then-insert).

    Validates each subscription before any DB write.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        user_id: Authenticated user ID from JWT.
        subscriptions: List of dicts with keys: region_code, alert_type, is_active (optional).

    Returns:
        List of inserted subscription dicts.

    Raises:
        ValueError: invalid alert_type, empty region_code, or duplicate (region_code, alert_type).
    """
    seen: set = set()
    validated: list = []

    for sub in subscriptions:
        region_code = (sub.get("region_code") or "").strip()
        alert_type = (sub.get("alert_type") or "").strip()
        is_active = bool(sub.get("is_active", True))

        if not region_code:
            raise ValueError("region_code cannot be empty")
        if alert_type not in VALID_ALERT_TYPES:
            raise ValueError(
                f"Invalid alert_type '{alert_type}'. "
                f"Must be one of: {sorted(VALID_ALERT_TYPES)}"
            )
        key = (region_code, alert_type)
        if key in seen:
            raise ValueError(
                f"Duplicate subscription: region_code='{region_code}', "
                f"alert_type='{alert_type}'"
            )
        seen.add(key)
        validated.append((region_code, alert_type, is_active))

    cursor = conn.cursor()
    cursor.execute("DELETE FROM ALERT_SUBSCRIPTION WHERE user_id = ?", (user_id,))

    result = []
    for region_code, alert_type, is_active in validated:
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

    cursor.execute(
        "UPDATE USER_ACCOUNT SET last_activity = ? WHERE id = ?",
        (datetime.now(timezone.utc), user_id),
    )
    conn.commit()
    return result
