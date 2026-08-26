"""
CSV Capacity Ingestion Module — Story 1.2, Task 1

Ingests regional installed capacity CSV files to Bronze layer.
Validates structure (non-empty, parseable headers), moves
malformed files to errors/, and logs audit entries.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Expected columns in capacity CSV (flexible — we check a minimum set)
REQUIRED_COLUMNS = {"code_insee_region", "puissance_installee_mw"}
RECOMMENDED_COLUMNS = {
    "libelle_region",
    "filiere",
    "source_energie",
    "date_mise_a_jour",
    "annee",
}


class CSVValidationError(Exception):
    """Raised when CSV validation fails."""

    def __init__(self, message: str, filename: str = ""):
        super().__init__(message)
        self.filename = filename


class CSVIngestion:
    """Ingest and validate capacity CSV files to Bronze layer."""

    def __init__(self, bronze_storage, audit_logger=None):
        """
        Args:
            bronze_storage: BronzeStorage instance for writing to Bronze.
            audit_logger: AuditLogger instance for heartbeat logging.
        """
        self.bronze = bronze_storage
        self.audit = audit_logger

    def ingest_file(self, filepath: str | Path) -> dict:
        """
        Ingest a single CSV file to Bronze layer.

        Args:
            filepath: Path to the CSV file.

        Returns:
            Audit log entry dict with status and details.
        """
        filepath = Path(filepath)
        filename = filepath.name
        logger.info("Ingesting CSV: %s", filename)

        try:
            # Read and validate
            content = filepath.read_text(encoding="utf-8-sig")  # handles BOM
            row_count = self._validate(content, filename)

            # Write raw CSV to Bronze (no transformation)
            bronze_path = self._write_to_bronze(content, filename)

            logger.info(
                "CSV ingested: %s → %s (%d rows)", filename, bronze_path, row_count
            )

            if self.audit:
                return self.audit.log_success(
                    record_count=row_count,
                    details={"filename": filename, "bronze_path": bronze_path},
                )
            return {"status": "success", "record_count": row_count, "path": bronze_path}

        except CSVValidationError as e:
            logger.error("CSV validation failed: %s — %s", filename, e)
            error_path = self._write_to_errors(
                filepath.read_text(encoding="utf-8-sig"), filename, str(e)
            )

            if self.audit:
                return self.audit.log_failure(
                    error=str(e),
                    details={"filename": filename, "error_path": error_path},
                )
            return {"status": "failure", "error": str(e), "error_path": error_path}

        except Exception as e:
            logger.error("Unexpected error ingesting %s: %s", filename, e)
            if self.audit:
                return self.audit.log_failure(
                    error=f"Unexpected: {e}",
                    details={"filename": filename},
                )
            return {"status": "failure", "error": str(e)}

    def ingest_directory(self, directory: str | Path) -> list[dict]:
        """Ingest all CSV files from a directory."""
        directory = Path(directory)
        results = []

        csv_files = sorted(directory.glob("*.csv"))
        if not csv_files:
            logger.warning("No CSV files found in %s", directory)
            return results

        for csv_file in csv_files:
            result = self.ingest_file(csv_file)
            results.append(result)

        success = sum(1 for r in results if r.get("status") == "success")
        logger.info(
            "Directory ingestion: %d/%d files succeeded", success, len(results)
        )
        return results

    def _validate(self, content: str, filename: str) -> int:
        """
        Validate CSV content.

        Returns:
            Number of data rows.

        Raises:
            CSVValidationError: If validation fails.
        """
        # Check not empty
        stripped = content.strip()
        if not stripped:
            raise CSVValidationError("File is empty", filename)

        # Check parseable
        try:
            reader = csv.DictReader(io.StringIO(stripped))
            headers = reader.fieldnames
        except csv.Error as e:
            raise CSVValidationError(f"CSV parse error: {e}", filename)

        if not headers:
            raise CSVValidationError("No headers found", filename)

        # Check required columns
        header_set = {h.strip().lower() for h in headers}
        missing = REQUIRED_COLUMNS - header_set
        if missing:
            raise CSVValidationError(
                f"Missing required columns: {missing}", filename
            )

        # Count rows
        rows = list(reader)
        if not rows:
            raise CSVValidationError("File has headers but no data rows", filename)

        return len(rows)

    def _write_to_bronze(self, content: str, filename: str) -> str:
        """Write raw CSV to Bronze layer."""
        ts = datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
        date_path = ts.strftime("%Y/%m")

        stem = Path(filename).stem
        dest_filename = f"{stem}_{ts_str}.csv"
        full_path = f"reference/capacity/{date_path}/{dest_filename}"

        if self.bronze.local_mode:
            dest = self.bronze.local_root / full_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            logger.info("Written (local): %s", dest)
            return str(dest)
        else:
            file_client = self.bronze.fs_client.get_file_client(full_path)
            file_client.upload_data(content.encode("utf-8"), overwrite=True)
            logger.info("Written (ADLS): bronze/%s", full_path)
            return f"bronze/{full_path}"

    def _write_to_errors(self, content: str, filename: str, error: str) -> str:
        """Write malformed CSV to errors directory."""
        ts = datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%SZ")

        stem = Path(filename).stem
        dest_filename = f"{stem}_{ts_str}_ERROR.csv"
        full_path = f"reference/capacity/errors/{dest_filename}"

        if self.bronze.local_mode:
            dest = self.bronze.local_root / full_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            # Also write error metadata
            meta_path = dest.with_suffix(".meta.json")
            import json

            meta_path.write_text(
                json.dumps(
                    {"filename": filename, "error": error, "timestamp": ts_str},
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("Written error file (local): %s", dest)
            return str(dest)
        else:
            file_client = self.bronze.fs_client.get_file_client(full_path)
            file_client.upload_data(content.encode("utf-8"), overwrite=True)
            return f"bronze/{full_path}"
