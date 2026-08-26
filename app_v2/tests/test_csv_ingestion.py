"""Tests for csv_ingestion.py — Story 1.2, Task 3"""


from pathlib import Path
from unittest.mock import MagicMock

import pytest

from functions.shared.bronze_storage import BronzeStorage
from functions.shared.csv_ingestion import CSVIngestion


@pytest.fixture
def local_storage(tmp_path):
    return BronzeStorage(local_mode=True, local_root=str(tmp_path))


@pytest.fixture
def ingestion(local_storage):
    audit = MagicMock()
    audit.log_success.return_value = {"status": "success", "record_count": 0}
    audit.log_failure.return_value = {"status": "failure", "error": ""}
    return CSVIngestion(bronze_storage=local_storage, audit_logger=audit)


@pytest.fixture
def sample_csv_path():
    return Path("tests/fixtures/capacity_sample.csv")


class TestCSVIngestionValid:
    """AC #1, #2: Valid CSV files are ingested and logged."""

    def test_ingest_valid_file(self, ingestion, sample_csv_path):
        """Valid CSV is ingested successfully."""
        result = ingestion.ingest_file(sample_csv_path)  # noqa: F841
        ingestion.audit.log_success.assert_called_once()
        call_kwargs = ingestion.audit.log_success.call_args
        assert call_kwargs[1]["record_count"] == 16

    def test_file_written_to_bronze(self, ingestion, sample_csv_path, local_storage, tmp_path):
        """CSV content is preserved in Bronze directory."""
        ingestion.ingest_file(sample_csv_path)
        # Check files exist in bronze/reference/capacity/
        capacity_files = list(tmp_path.rglob("*.csv"))
        assert len(capacity_files) == 1
        content = capacity_files[0].read_text(encoding="utf-8")
        assert "code_insee_region" in content
        assert "puissance_installee_mw" in content

    def test_bronze_path_convention(self, ingestion, sample_csv_path, tmp_path):
        """Path follows reference/capacity/YYYY/MM/ convention."""
        ingestion.ingest_file(sample_csv_path)
        capacity_files = list(tmp_path.rglob("*.csv"))
        path_str = str(capacity_files[0])
        assert "reference/capacity/" in path_str


class TestCSVIngestionErrors:
    """AC #3: Malformed files are moved to errors/."""

    def test_empty_file(self, ingestion, tmp_path):
        """Empty CSV triggers validation error."""
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        result = ingestion.ingest_file(empty)  # noqa: F841
        ingestion.audit.log_failure.assert_called_once()
        assert "empty" in ingestion.audit.log_failure.call_args[1]["error"].lower()

    def test_headers_only(self, ingestion, tmp_path):
        """CSV with headers but no data rows fails."""
        headers_only = tmp_path / "headers_only.csv"
        headers_only.write_text(
            "code_insee_region,puissance_installee_mw\n", encoding="utf-8"
        )
        result = ingestion.ingest_file(headers_only)  # noqa: F841
        ingestion.audit.log_failure.assert_called_once()

    def test_missing_required_column(self, ingestion, tmp_path):
        """CSV without required columns fails."""
        bad_csv = tmp_path / "bad_columns.csv"
        bad_csv.write_text(
            "region,valeur\n11,100\n24,200\n", encoding="utf-8"
        )
        result = ingestion.ingest_file(bad_csv)  # noqa: F841
        ingestion.audit.log_failure.assert_called_once()
        error_msg = ingestion.audit.log_failure.call_args[1]["error"]
        assert "required" in error_msg.lower()

    def test_error_file_created(self, ingestion, tmp_path):
        """Malformed file is written to errors/ directory."""
        bad = tmp_path / "malformed.csv"
        bad.write_text("", encoding="utf-8")
        ingestion.ingest_file(bad)
        error_files = list(
            (ingestion.bronze.local_root / "reference/capacity/errors").rglob("*")
        )
        assert len(error_files) > 0


class TestCSVIngestionDirectory:
    """Test batch directory ingestion."""

    def test_ingest_directory(self, ingestion, tmp_path):
        """All CSVs in directory are processed."""
        landing = tmp_path / "landing"
        landing.mkdir()
        (landing / "file1.csv").write_text(
            "code_insee_region,puissance_installee_mw\n11,100\n", encoding="utf-8"
        )
        (landing / "file2.csv").write_text(
            "code_insee_region,puissance_installee_mw\n24,200\n", encoding="utf-8"
        )
        results = ingestion.ingest_directory(landing)
        assert len(results) == 2

    def test_empty_directory(self, ingestion, tmp_path):
        """Empty directory returns empty results."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        results = ingestion.ingest_directory(empty_dir)
        assert len(results) == 0
