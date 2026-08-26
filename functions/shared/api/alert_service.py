"""
Alert Service — Story 5.2, Task 2.2

Reads alerts from AlertStore and formats them for the API response.
AC #1: Returns active alerts for the dashboard to display.
AC #2: All alerts come from the audit trail written by AlertEngine.
"""

import logging
import os
from pathlib import Path
from typing import Any

from shared.alerting.alert_store import AlertStore

logger = logging.getLogger(__name__)


def _get_store() -> AlertStore:
    base = os.environ.get("BRONZE_BASE_PATH", "bronze")
    return AlertStore(base_path=base)


def query_alerts(
    region_code: str | None = None,
    status: str | None = "active",
    days: int = 7,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Fetch recent alerts from the store.

    Args:
        region_code: Filter by region (optional).
        status: 'active', 'acknowledged', or None for all.
        days: Look-back window in days.
        limit: Maximum alerts to return.

    Returns:
        Dict with 'alerts' list and 'total' count.
    """
    store = _get_store()
    alerts = store.read_recent(days=days, region=region_code, status=status)
    alerts = alerts[:limit]
    return {
        "alerts": alerts,
        "total": len(alerts),
        "status_filter": status,
        "region_filter": region_code,
    }
