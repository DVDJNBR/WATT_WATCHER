"""Tests for maintenance_scraper.py — Story 2.1, Task 4"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from functions.shared.maintenance_scraper import MaintenanceScraper, ScraperError


FIXTURE_PATH = Path("tests/fixtures/rte_maintenance_page.html")


@pytest.fixture
def scraper():
    return MaintenanceScraper()


class TestParseHTML:
    """AC #1, #2, #4: HTML parsing extracts structured maintenance events."""

    def test_parse_fixture(self, scraper):
        """All 6 events are extracted from fixture."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        assert len(events) == 6

    def test_event_structure(self, scraper):
        """Each event has required fields (AC #2)."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        required_fields = {
            "event_id", "start_date", "end_date", "description",
            "affected_area", "source_url", "scraped_at",
        }
        for event in events:
            for field in required_fields:
                assert field in event, f"Missing field: {field}"

    def test_event_id_extraction(self, scraper):
        """Event IDs are correctly parsed."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        ids = [e["event_id"] for e in events]
        assert "EVT-2026-001" in ids
        assert "EVT-2026-006" in ids

    def test_mw_parsing(self, scraper):
        """MW values are parsed as floats."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        gravelines = next(e for e in events if e["event_id"] == "EVT-2026-001")
        assert gravelines["unavailable_mw"] == 910.0

    def test_area_extraction(self, scraper):
        """Affected areas are correctly parsed."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        areas = {e["affected_area"] for e in events}
        assert "Normandie" in areas
        assert "Grand Est" in areas

    def test_event_types(self, scraper):
        """Event types (Planifiée/Fortuite) are parsed."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        types = {e["event_type"] for e in events}
        assert "Planifiée" in types
        assert "Fortuite" in types

    def test_scraped_at_present(self, scraper):
        """Each event has scraped_at timestamp."""
        events = scraper.scrape_from_file(FIXTURE_PATH)
        for event in events:
            assert event["scraped_at"]  # non-empty


class TestErrorHandling:
    """AC #3: HTTP errors handled gracefully."""

    def test_404_raises(self, scraper):
        """Non-retryable 404 raises ScraperError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        with patch.object(scraper.session, "get", return_value=mock_resp):
            with pytest.raises(ScraperError, match="404"):
                scraper.scrape_from_url("https://example.com")

    def test_429_retries(self, scraper):
        """Retryable 429 triggers retry then succeeds."""
        mock_429 = MagicMock()
        mock_429.status_code = 429

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = FIXTURE_PATH.read_text()

        with patch.object(
            scraper.session, "get", side_effect=[mock_429, mock_200]
        ):
            with patch("functions.shared.maintenance_scraper.time.sleep"):
                events = scraper.scrape_from_url("https://example.com")

        assert len(events) == 6

    def test_no_url_raises(self):
        """Scraping without URL raises ScraperError."""
        scraper = MaintenanceScraper()
        with pytest.raises(ScraperError, match="No URL"):
            scraper.scrape_from_url()

    def test_empty_html(self, scraper):
        """Empty HTML returns empty list."""
        events = scraper.parse_html("<html><body></body></html>")
        assert events == []
