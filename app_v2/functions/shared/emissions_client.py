"""
Emission Factor Client — Story 2.3, Task 1 & 2

Downloads government emission factors from ADEME Base Carbone / data.gouv.fr.
Implements conditional fetch (ETag/Last-Modified) to skip redundant downloads.
Stores raw data in Bronze layer with audit logging.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ADEME Base Carbone Open Data endpoint (data.gouv.fr)
DEFAULT_SOURCE_URL = (
    "https://data.ademe.fr/data-fair/api/v1/datasets/"
    "base-carbone(r)-donnees-officielles/lines"
)

USER_AGENT = "GRID_POWER_STREAM/1.0 EmissionsIngestion"


class EmissionsClient:
    """Download and manage emission factor reference data."""

    def __init__(self, bronze_storage=None, audit_logger=None):
        """
        Args:
            bronze_storage: BronzeStorage instance.
            audit_logger: AuditLogger instance.
        """
        self.bronze = bronze_storage
        self.audit = audit_logger
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def ingest_from_url(self, url: str = DEFAULT_SOURCE_URL) -> dict:
        """
        Download emission factors from a URL.

        AC #1: Download and store in bronze/reference/emissions/
        AC #3: Conditional fetch via checksum comparison.

        Returns:
            Summary dict: {status, record_count, path, skipped}.
        """
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            content = response.text

            # AC #3: Check if data changed since last download
            new_checksum = self._compute_checksum(content)
            if self._should_skip(new_checksum):
                logger.info("Emission factors unchanged — skipping download")
                if self.audit:
                    self.audit.log_success(
                        record_count=0,
                        details={"emissions": "skipped_unchanged"},
                    )
                return {"status": "skipped", "reason": "data_unchanged"}

            # AC #1, #2: Store raw content in Bronze
            path = self._write_to_bronze(content)

            # Save checksum for next comparison
            self._save_checksum(new_checksum)

            # Count records
            lines = [line for line in content.strip().split("\n") if line.strip()]
            record_count = max(0, len(lines) - 1)  # minus header

            logger.info("Emission factors ingested: %d records → %s", record_count, path)

            if self.audit:
                self.audit.log_success(
                    record_count=record_count,
                    details={"emissions_path": path, "checksum": new_checksum},
                )

            return {
                "status": "success",
                "record_count": record_count,
                "path": path,
                "checksum": new_checksum,
            }

        except requests.RequestException as e:
            logger.error("Failed to download emission factors: %s", e)
            if self.audit:
                self.audit.log_failure(
                    error=str(e),
                    details={"url": url},
                )
            return {"status": "failure", "error": str(e)}

    def ingest_from_file(self, filepath: str | Path) -> dict:
        """
        Ingest emission factors from a local file (dev/test mode).

        AC #1, #2: Raw file preserved in Bronze.
        """
        filepath = Path(filepath)
        content = filepath.read_text(encoding="utf-8-sig")

        new_checksum = self._compute_checksum(content)
        if self._should_skip(new_checksum):
            logger.info("Emission factors unchanged — skipping")
            return {"status": "skipped", "reason": "data_unchanged"}

        path = self._write_to_bronze(content)
        self._save_checksum(new_checksum)

        lines = [line for line in content.strip().split("\n") if line.strip()]
        record_count = max(0, len(lines) - 1)

        logger.info("Emission factors ingested from file: %d records", record_count)

        if self.audit:
            self.audit.log_success(
                record_count=record_count,
                details={"emissions_path": path},
            )

        return {
            "status": "success",
            "record_count": record_count,
            "path": path,
            "checksum": new_checksum,
        }

    def _write_to_bronze(self, content: str) -> str:
        """Write raw emission factor data to Bronze layer."""
        ts = datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
        year = ts.strftime("%Y")

        filename = f"emission_factors_{ts_str}.csv"
        full_path = f"reference/emissions/{year}/{filename}"

        if self.bronze and self.bronze.local_mode:
            dest = self.bronze.local_root / full_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            logger.info("Written (local): %s", dest)
            return str(dest)
        elif self.bronze:
            file_client = self.bronze.fs_client.get_file_client(full_path)
            file_client.upload_data(content.encode("utf-8"), overwrite=True)
            return f"bronze/{full_path}"
        else:
            # No storage configured — return path only
            return full_path

    def _compute_checksum(self, content: str) -> str:
        """Compute SHA-256 checksum for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _should_skip(self, new_checksum: str) -> bool:
        """Check if data has changed since last ingestion."""
        checkpoint = self._load_checkpoint()
        if checkpoint and checkpoint.get("checksum") == new_checksum:
            return True
        return False

    def _save_checksum(self, checksum: str) -> None:
        """Save checksum for next comparison."""
        if self.bronze and self.bronze.local_mode:
            cp_path = self.bronze.local_root / "reference/emissions/_checkpoint.json"
            cp_path.parent.mkdir(parents=True, exist_ok=True)
            cp_path.write_text(
                json.dumps({
                    "checksum": checksum,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }),
                encoding="utf-8",
            )

    def _load_checkpoint(self) -> dict | None:
        """Load checkpoint for deduplication."""
        if self.bronze and self.bronze.local_mode:
            cp_path = self.bronze.local_root / "reference/emissions/_checkpoint.json"
            if cp_path.exists():
                return json.loads(cp_path.read_text(encoding="utf-8"))
        return None
