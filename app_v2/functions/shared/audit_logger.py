"""
Audit Logger Module — Story 1.1, Task 5

Structured logging for ingestion pipeline.
Logs to both Python logging (→ Application Insights) and Bronze audit files.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """Structured audit logging for data ingestion pipeline."""

    def __init__(self, source: str = "rte_eco2mix", bronze_storage=None):
        """
        Args:
            source: Data source identifier for log entries.
            bronze_storage: BronzeStorage instance for persisting audit logs.
                           If None, logs only to Python logging.
        """
        self.source = source
        self.bronze_storage = bronze_storage

    def log_success(
        self,
        record_count: int,
        job_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict:
        """Log a successful ingestion run."""
        entry = self._build_entry(
            status="success",
            record_count=record_count,
            job_id=job_id,
            details=details,
        )
        logger.info(
            "Ingestion SUCCESS: source=%s, records=%d, job_id=%s",
            self.source,
            record_count,
            entry["job_id"],
        )
        self._persist(entry)
        return entry

    def log_failure(
        self,
        error: str,
        job_id: str | None = None,
        record_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> dict:
        """Log a failed ingestion run."""
        entry = self._build_entry(
            status="failure",
            record_count=record_count,
            job_id=job_id,
            error_details=error,
            details=details,
        )
        logger.error(
            "Ingestion FAILURE: source=%s, error=%s, job_id=%s",
            self.source,
            error,
            entry["job_id"],
        )
        self._persist(entry)
        return entry

    def _build_entry(
        self,
        status: str,
        record_count: int = 0,
        job_id: str | None = None,
        error_details: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict:
        """Build a structured audit log entry."""
        entry = {
            "job_id": job_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self.source,
            "status": status,
            "record_count": record_count,
        }
        if error_details:
            entry["error_details"] = error_details
        if details:
            entry["details"] = details
        return entry

    def _persist(self, entry: dict) -> None:
        """Persist audit entry to Bronze storage if available."""
        if self.bronze_storage:
            try:
                self.bronze_storage.write_audit(entry)
            except Exception as e:
                logger.warning("Failed to persist audit log: %s", e)
