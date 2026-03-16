"""
Alert Store — Story 5.2, Task 2

Persists alert dicts as JSON files under:
  {base_path}/audit/alerts/YYYY-MM-DD/{alert_id}.json

Reads are date-range filtered for the API endpoint.
AC #2: All alerts are written to the audit trail.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path("bronze")


class AlertStore:
    """File-based alert persistence (bronze/audit/alerts/)."""

    def __init__(self, base_path: str | Path | None = None):
        self.base = Path(base_path) if base_path else _DEFAULT_BASE
        self.alerts_root = self.base / "audit" / "alerts"

    def save(self, alerts: list[dict[str, Any]]) -> int:
        """Persist a list of alerts. Returns count saved."""
        if not alerts:
            return 0
        saved = 0
        for alert in alerts:
            ts = alert.get("timestamp", datetime.now(timezone.utc).isoformat())
            date_str = ts[:10]  # YYYY-MM-DD
            day_dir = self.alerts_root / date_str
            day_dir.mkdir(parents=True, exist_ok=True)
            file_path = day_dir / f"{alert['alert_id']}.json"
            file_path.write_text(json.dumps(alert, ensure_ascii=False), encoding="utf-8")
            saved += 1
        logger.info("AlertStore: saved %d alert(s)", saved)
        return saved

    def read_recent(
        self,
        days: int = 7,
        region: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Read alerts from the last N days.

        Args:
            days: How many days back to search.
            region: Filter by code_insee region (optional).
            status: 'active' → non-acknowledged; 'acknowledged' → acknowledged.

        Returns:
            List of alert dicts sorted by timestamp desc.
        """
        if not self.alerts_root.exists():
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        alerts: list[dict[str, Any]] = []

        for day_dir in sorted(self.alerts_root.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            try:
                day_date = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if day_date < cutoff:
                break
            for file in day_dir.glob("*.json"):
                try:
                    alert = json.loads(file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue

                if region and alert.get("region") != region:
                    continue
                if status == "active" and alert.get("acknowledged"):
                    continue
                if status == "acknowledged" and not alert.get("acknowledged"):
                    continue

                alerts.append(alert)

        alerts.sort(key=lambda a: a.get("timestamp", ""), reverse=True)
        return alerts
