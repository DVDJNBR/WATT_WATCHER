"""
Asset Lifecycle Module — Story 1.3, Task 3

Detects stale and inactive assets based on configurable thresholds.
- Regions not seen for STALENESS_THRESHOLD_HOURS → status='stale'
- Regions not seen for INACTIVE_THRESHOLD_HOURS → status='inactive'

Soft-delete pattern: no DELETE statements, preserves FK integrity.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Configurable thresholds via env vars
DEFAULT_STALENESS_HOURS = 24
DEFAULT_INACTIVE_HOURS = 168  # 7 days


class AssetLifecycle:
    """Manage asset lifecycle: detect and mark stale/inactive assets."""

    def __init__(self, db_connection: Any, audit_logger=None):
        """
        Args:
            db_connection: Database connection (psycopg2 or sqlite3).
            audit_logger: Optional AuditLogger instance.
        """
        self.conn = db_connection
        self.audit = audit_logger
        self._is_sqlite = isinstance(db_connection, sqlite3.Connection)

        self.staleness_hours = int(
            os.environ.get("STALENESS_THRESHOLD_HOURS", DEFAULT_STALENESS_HOURS)
        )
        self.inactive_hours = int(
            os.environ.get("INACTIVE_THRESHOLD_HOURS", DEFAULT_INACTIVE_HOURS)
        )

    def check_staleness(self, now: datetime | None = None) -> dict:
        """
        Check all active regions for staleness and update status.

        Args:
            now: Current time (for testing). Defaults to UTC now.

        Returns:
            Summary: {stale_count, inactive_count, details}.
        """
        now = now or datetime.now(timezone.utc)
        stale_threshold = now - timedelta(hours=self.staleness_hours)
        inactive_threshold = now - timedelta(hours=self.inactive_hours)

        cursor = self.conn.cursor()

        # Mark inactive (not seen for > inactive_threshold)
        inactive_regions = self._mark_inactive(cursor, inactive_threshold)

        # Mark stale (not seen for > stale_threshold, still active)
        stale_regions = self._mark_stale(cursor, stale_threshold)

        self.conn.commit()

        summary = {
            "stale_count": len(stale_regions),
            "inactive_count": len(inactive_regions),
            "stale_regions": stale_regions,
            "inactive_regions": inactive_regions,
        }

        if stale_regions or inactive_regions:
            logger.warning(
                "Lifecycle update: %d stale, %d inactive",
                len(stale_regions),
                len(inactive_regions),
            )
        else:
            logger.info("Lifecycle check: all regions are active")

        if self.audit:
            if stale_regions or inactive_regions:
                self.audit.log_success(
                    record_count=len(stale_regions) + len(inactive_regions),
                    details={"lifecycle": summary},
                )
            else:
                self.audit.log_success(
                    record_count=0,
                    details={"lifecycle": "all_active"},
                )

        return summary

    def _mark_stale(self, cursor, threshold: datetime) -> list[str]:
        """Mark active regions as stale if last_seen_at < threshold."""
        if self._is_sqlite:
            cursor.execute(
                """SELECT code_insee_region FROM DIM_REGION
                   WHERE status = 'active' AND last_seen_at < ?""",
                (threshold.isoformat(),),
            )
        else:
            cursor.execute(
                """SELECT code_insee_region FROM DIM_REGION
                   WHERE status = 'active' AND last_seen_at < %s""",
                (threshold,),
            )

        stale = [row[0] for row in cursor.fetchall()]

        if stale:
            if self._is_sqlite:
                placeholders = ",".join(["?"] * len(stale))
            else:
                placeholders = ",".join(["%s"] * len(stale))
            cursor.execute(
                f"UPDATE DIM_REGION SET status = 'stale' "
                f"WHERE code_insee_region IN ({placeholders})",
                stale,
            )
            for code in stale:
                logger.warning("Region %s → STALE", code)

        return stale

    def _mark_inactive(self, cursor, threshold: datetime) -> list[str]:
        """Mark stale regions as inactive if last_seen_at < threshold."""
        if self._is_sqlite:
            cursor.execute(
                """SELECT code_insee_region FROM DIM_REGION
                   WHERE status IN ('active', 'stale') AND last_seen_at < ?""",
                (threshold.isoformat(),),
            )
        else:
            cursor.execute(
                """SELECT code_insee_region FROM DIM_REGION
                   WHERE status IN ('active', 'stale') AND last_seen_at < %s""",
                (threshold,),
            )

        inactive = [row[0] for row in cursor.fetchall()]

        if inactive:
            if self._is_sqlite:
                placeholders = ",".join(["?"] * len(inactive))
            else:
                placeholders = ",".join(["%s"] * len(inactive))
            cursor.execute(
                f"UPDATE DIM_REGION SET status = 'inactive' "
                f"WHERE code_insee_region IN ({placeholders})",
                inactive,
            )
            for code in inactive:
                logger.warning("Region %s → INACTIVE", code)

        return inactive

    def get_status_summary(self) -> dict:
        """Get count of regions by status."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT status, COUNT(*) FROM DIM_REGION GROUP BY status"
        )
        return dict(cursor.fetchall())
