"""Tests for bronze_storage.py — Story 1.1, Task 4.3"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from functions.shared.bronze_storage import BronzeStorage


@pytest.fixture
def local_storage(tmp_path):
    """BronzeStorage in local mode with temp directory."""
    return BronzeStorage(local_mode=True, local_root=str(tmp_path))


@pytest.fixture
def sample_records():
    """Load fixture from Story 0.1."""
    with open("tests/fixtures/rte_eco2mix_regional_sample.json") as f:
        return json.load(f)


class TestBronzeStorageLocal:
    """Test local filesystem mode."""

    def test_write_json_creates_file(self, local_storage, sample_records, tmp_path):
        """AC #1: Raw JSON is saved as timestamped file."""
        ts = datetime(2025, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        path = local_storage.write_json(sample_records, timestamp=ts)

        assert Path(path).exists()
        assert "2025/03/15" in path
        assert "eco2mix_regional_20250315T103000Z" in path

    def test_write_json_content_matches(self, local_storage, sample_records, tmp_path):
        """Stored content matches input data."""
        path = local_storage.write_json(sample_records)
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        assert stored == sample_records

    def test_write_json_path_convention(self, local_storage, sample_records, tmp_path):
        """Path follows bronze/rte/production/YYYY/MM/DD/ convention."""
        ts = datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
        path = local_storage.write_json(sample_records, timestamp=ts)
        assert "rte/production/2025/12/01/" in path

    def test_write_audit_creates_file(self, local_storage, tmp_path):
        """AC #2: Audit heartbeat file is created."""
        audit_entry = {
            "job_id": "test-123",
            "status": "success",
            "record_count": 42,
        }
        path = local_storage.write_audit(audit_entry)

        assert Path(path).exists()
        assert "audit/ingestion/" in path
        assert "heartbeat_" in path

    def test_write_audit_content(self, local_storage, tmp_path):
        """Audit entry content is preserved."""
        entry = {"job_id": "abc", "status": "failure", "error": "timeout"}
        path = local_storage.write_audit(entry)
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        assert stored["job_id"] == "abc"
        assert stored["status"] == "failure"
