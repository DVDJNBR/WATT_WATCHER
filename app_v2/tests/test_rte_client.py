"""Tests for rte_client.py — Story 1.1, Task 2.4"""

import json
from unittest.mock import MagicMock, patch

import pytest

from functions.shared.rte_client import RTEClient, RTEClientError


@pytest.fixture
def client():
    return RTEClient()


@pytest.fixture
def sample_response():
    """Load fixture from Story 0.1."""
    with open("tests/fixtures/rte_eco2mix_regional_sample.json") as f:
        records = json.load(f)
    return {"total_count": len(records), "results": records}


class TestFetchEco2mixRegional:
    """Test fetch_eco2mix_regional with various scenarios."""

    def test_success(self, client, sample_response):
        """AC #1: Successful API call returns records."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_response

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.fetch_eco2mix_regional()

        assert "results" in result
        assert "total_count" in result
        assert len(result["results"]) > 0

    def test_success_with_region_filter(self, client, sample_response):
        """Filter by region code."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_response

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.fetch_eco2mix_regional(region_code="11")

        call_params = mock_get.call_args[1]["params"]
        assert "code_insee_region = '11'" in call_params.get("where", "")

    def test_429_retries_then_succeeds(self, client, sample_response):
        """AC #3: Retryable 429 triggers backoff then succeeds."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = sample_response

        with patch.object(
            client.session, "get", side_effect=[mock_429, mock_200]
        ):
            with patch("functions.shared.rte_client.time.sleep"):
                result = client.fetch_eco2mix_regional()

        assert result["total_count"] > 0

    def test_500_retries_exhausted(self, client):
        """AC #3: Max retries exhausted raises RTEClientError."""
        mock_500 = MagicMock()
        mock_500.status_code = 500
        mock_500.text = "Internal Server Error"

        with patch.object(
            client.session, "get", return_value=mock_500
        ):
            with patch("functions.shared.rte_client.time.sleep"):
                with pytest.raises(RTEClientError, match="Max retries"):
                    client.fetch_eco2mix_regional()

    def test_400_no_retry(self, client):
        """Non-retryable 400 fails immediately."""
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.text = "Bad Request"

        with patch.object(client.session, "get", return_value=mock_400):
            with pytest.raises(RTEClientError, match="Non-retryable"):
                client.fetch_eco2mix_regional()

    def test_timeout_retries(self, client, sample_response):
        """Network timeout triggers retry."""
        import requests

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = sample_response

        with patch.object(
            client.session,
            "get",
            side_effect=[requests.exceptions.Timeout, mock_200],
        ):
            with patch("functions.shared.rte_client.time.sleep"):
                result = client.fetch_eco2mix_regional()

        assert result["total_count"] > 0


class TestFetchAllRecent:
    """Test pagination logic."""

    def test_single_page(self, client):
        """All records fit in one page."""
        response = {"total_count": 2, "results": [{"a": 1}, {"b": 2}]}

        with patch.object(client, "fetch_eco2mix_regional", return_value=response):
            records = client.fetch_all_recent(minutes=30)

        assert len(records) == 2

    def test_multi_page(self, client):
        """Records span multiple pages."""
        page1 = {"total_count": 3, "results": [{"a": 1}, {"b": 2}]}
        page2 = {"total_count": 3, "results": [{"c": 3}]}

        with patch.object(
            client, "fetch_eco2mix_regional", side_effect=[page1, page2]
        ):
            records = client.fetch_all_recent(minutes=60)

        assert len(records) == 3
