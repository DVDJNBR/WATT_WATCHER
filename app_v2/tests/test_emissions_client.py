"""Tests for emissions_client.py — Story 2.3, Task 3"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from functions.shared.bronze_storage import BronzeStorage
from functions.shared.emissions_client import EmissionsClient


FIXTURE_PATH = Path("tests/fixtures/emission_factors_sample.csv")


@pytest.fixture
def local_storage(tmp_path):
    return BronzeStorage(local_mode=True, local_root=str(tmp_path))


@pytest.fixture
def client(local_storage):
    audit = MagicMock()
    audit.log_success.return_value = {"status": "success"}
    audit.log_failure.return_value = {"status": "failure"}
    return EmissionsClient(bronze_storage=local_storage, audit_logger=audit)


class TestEmissionsIngestion:
    """AC #1, #2: Emission factor data is downloaded and stored."""

    def test_ingest_from_file(self, client):
        """Local file ingestion produces success result."""
        result = client.ingest_from_file(FIXTURE_PATH)
        assert result["status"] == "success"
        assert result["record_count"] == 12

    def test_raw_content_preserved(self, client, tmp_path):
        """AC #2: Original CSV format preserved in Bronze."""
        client.ingest_from_file(FIXTURE_PATH)
        output_files = list(tmp_path.rglob("*.csv"))
        assert len(output_files) == 1
        content = output_files[0].read_text(encoding="utf-8")
        assert "facteur_emission_co2_kg_mwh" in content
        assert "nucleaire" in content
        assert "gaz_naturel" in content

    def test_bronze_path_convention(self, client, tmp_path):
        """Stored in reference/emissions/YYYY/ path."""
        client.ingest_from_file(FIXTURE_PATH)
        output_files = list(tmp_path.rglob("*.csv"))
        path_str = str(output_files[0])
        assert "reference/emissions/" in path_str

    def test_audit_logged(self, client):
        """Audit logger called on success."""
        client.ingest_from_file(FIXTURE_PATH)
        client.audit.log_success.assert_called_once()


class TestConditionalFetch:
    """AC #3: Conditional fetch skips unchanged data."""

    def test_skip_unchanged_data(self, client):
        """Second ingestion of same data is skipped."""
        result1 = client.ingest_from_file(FIXTURE_PATH)
        assert result1["status"] == "success"

        result2 = client.ingest_from_file(FIXTURE_PATH)
        assert result2["status"] == "skipped"
        assert result2["reason"] == "data_unchanged"

    def test_download_changed_data(self, client, tmp_path):
        """Changed data triggers new download."""
        client.ingest_from_file(FIXTURE_PATH)

        # Create modified file
        modified = tmp_path / "modified.csv"
        content = FIXTURE_PATH.read_text() + "\nnouvelle,source,999.0,0.0,0.0,TEST,2025,2025-06-01\n"
        modified.write_text(content, encoding="utf-8")

        result = client.ingest_from_file(modified)
        assert result["status"] == "success"
        assert result["record_count"] == 13


class TestHTTPDownload:
    """Test URL-based download with mocked HTTP."""

    def test_ingest_from_url_success(self, client):
        """Successful HTTP download stores data."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = FIXTURE_PATH.read_text()
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.ingest_from_url("https://example.com/data.csv")

        assert result["status"] == "success"
        assert result["record_count"] == 12

    def test_ingest_from_url_error(self, client):
        """HTTP error returns failure."""
        import requests

        with patch.object(
            client.session, "get",
            side_effect=requests.RequestException("Connection refused"),
        ):
            result = client.ingest_from_url("https://example.com/data.csv")

        assert result["status"] == "failure"
        client.audit.log_failure.assert_called_once()
