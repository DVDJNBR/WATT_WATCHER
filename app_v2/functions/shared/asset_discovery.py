"""
Asset Discovery Module — Story 1.3, Task 2

Compares regions found in Bronze RTE data against the SQL DIM_REGION table.
- New regions → INSERT with status='active', first_seen_at=NOW()
- Known regions → UPDATE last_seen_at=NOW()

Supports both PostgreSQL/Supabase (psycopg2) and local SQLite for development.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class DBConnection(Protocol):
    """Protocol for database connections (works with psycopg2 and sqlite3)."""

    def cursor(self) -> Any: ...
    def commit(self) -> None: ...


class AssetDiscovery:
    """Discover and register grid assets from Bronze data."""

    def __init__(self, db_connection: Any, audit_logger=None):
        """
        Args:
            db_connection: Database connection (psycopg2 or sqlite3).
            audit_logger: Optional AuditLogger instance.
        """
        self.conn = db_connection
        self.audit = audit_logger
        self._is_sqlite = isinstance(db_connection, sqlite3.Connection)

    def discover_regions(self, bronze_records: list[dict]) -> dict:
        """
        Compare Bronze API records against DIM_REGION and sync.

        Args:
            bronze_records: List of raw API records containing
                          'code_insee_region' and 'libelle_region'.

        Returns:
            Summary dict: {new_count, updated_count, regions_seen}.
        """
        # Extract unique regions from Bronze data
        seen_regions = {}
        for record in bronze_records:
            code = str(record.get("code_insee_region", "")).strip()
            label = record.get("libelle_region", "").strip()
            if code and code not in seen_regions:
                seen_regions[code] = label

        if not seen_regions:
            logger.warning("No regions found in Bronze data")
            return {"new_count": 0, "updated_count": 0, "regions_seen": []}

        # Get existing regions from SQL
        existing = self._get_existing_regions()
        existing_codes = {r["code_insee_region"] for r in existing}

        new_count = 0
        updated_count = 0
        now = datetime.now(timezone.utc)

        cursor = self.conn.cursor()

        for code, label in seen_regions.items():
            if code not in existing_codes:
                # New region — INSERT
                self._insert_region(cursor, code, label, now)
                new_count += 1
                logger.info("NEW region discovered: %s (%s)", code, label)
            else:
                # Existing — UPDATE last_seen_at
                self._update_last_seen(cursor, code, now)
                updated_count += 1

        self.conn.commit()

        summary = {
            "new_count": new_count,
            "updated_count": updated_count,
            "regions_seen": list(seen_regions.keys()),
        }

        logger.info(
            "Discovery complete: %d new, %d updated, %d total",
            new_count,
            updated_count,
            len(seen_regions),
        )

        if self.audit:
            self.audit.log_success(
                record_count=len(seen_regions),
                details={"discovery": summary},
            )

        return summary

    def _get_existing_regions(self) -> list[dict]:
        """Get all regions currently in DIM_REGION."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT code_insee_region, libelle_region, status FROM DIM_REGION")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _insert_region(
        self, cursor, code: str, label: str, now: datetime
    ) -> None:
        """Insert a newly discovered region."""
        if self._is_sqlite:
            cursor.execute(
                """INSERT INTO DIM_REGION
                   (code_insee_region, libelle_region, status, first_seen_at, last_seen_at)
                   VALUES (?, ?, 'active', ?, ?)""",
                (code, label, now.isoformat(), now.isoformat()),
            )
        else:
            cursor.execute(
                """INSERT INTO DIM_REGION
                   (code_insee_region, libelle_region, status, first_seen_at, last_seen_at)
                   VALUES (%s, %s, 'active', %s, %s)""",
                (code, label, now, now),
            )

    def _update_last_seen(self, cursor, code: str, now: datetime) -> None:
        """Update last_seen_at and ensure status is active."""
        if self._is_sqlite:
            cursor.execute(
                """UPDATE DIM_REGION
                   SET last_seen_at = ?, status = 'active'
                   WHERE code_insee_region = ?""",
                (now.isoformat(), code),
            )
        else:
            cursor.execute(
                """UPDATE DIM_REGION
                   SET last_seen_at = %s, status = 'active'
                   WHERE code_insee_region = %s""",
                (now, code),
            )
