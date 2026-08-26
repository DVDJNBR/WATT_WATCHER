"""Tests for audit_logger.py — Story 1.1, Task 5.3"""

from unittest.mock import MagicMock

import pytest

from functions.shared.audit_logger import AuditLogger


@pytest.fixture
def logger_no_storage():
    return AuditLogger(source="test_source")


@pytest.fixture
def logger_with_storage():
    mock_storage = MagicMock()
    return AuditLogger(source="test_source", bronze_storage=mock_storage)


class TestAuditLogger:
    def test_log_success_returns_entry(self, logger_no_storage):
        """AC #2: Success creates heartbeat entry."""
        entry = logger_no_storage.log_success(record_count=42)

        assert entry["status"] == "success"
        assert entry["record_count"] == 42
        assert entry["source"] == "test_source"
        assert "job_id" in entry
        assert "timestamp" in entry

    def test_log_failure_returns_entry(self, logger_no_storage):
        """AC #3: Failure logged with error details."""
        entry = logger_no_storage.log_failure(error="HTTP 500")

        assert entry["status"] == "failure"
        assert entry["error_details"] == "HTTP 500"
        assert entry["record_count"] == 0

    def test_log_success_persists(self, logger_with_storage):
        """Audit entry is persisted to bronze storage."""
        logger_with_storage.log_success(record_count=10)
        logger_with_storage.bronze_storage.write_audit.assert_called_once()

    def test_log_failure_persists(self, logger_with_storage):
        """Failure entry is also persisted."""
        logger_with_storage.log_failure(error="timeout")
        logger_with_storage.bronze_storage.write_audit.assert_called_once()

    def test_custom_job_id(self, logger_no_storage):
        """Custom job_id is used when provided."""
        entry = logger_no_storage.log_success(record_count=1, job_id="my-job-123")
        assert entry["job_id"] == "my-job-123"

    def test_persist_failure_does_not_raise(self, logger_with_storage):
        """Storage failure doesn't crash the logger."""
        logger_with_storage.bronze_storage.write_audit.side_effect = Exception("disk full")
        # Should not raise
        entry = logger_with_storage.log_success(record_count=5)
        assert entry["status"] == "success"
