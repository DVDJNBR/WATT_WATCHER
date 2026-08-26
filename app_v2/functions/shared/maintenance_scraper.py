"""
Grid Maintenance Scraper — Story 2.1, Task 1

Scrapes scheduled/unscheduled production unavailability events
from RTE transparency portals using parsel (CSS + XPath selectors).

Demonstrates C8 competency: programmatic web scraping as data source.

Supports:
- Live scraping from a URL
- Local HTML file parsing (dev/test mode)
"""

import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from parsel import Selector

logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────
USER_AGENT = "GRID_POWER_STREAM/1.0 MaintenanceScraper"
POLITENESS_DELAY = 2.0  # seconds between requests
MAX_RETRIES = 3
BASE_DELAY = 2.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ScraperError(Exception):
    """Base exception for scraper errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MaintenanceScraper:
    """Scrape grid maintenance/unavailability events from transparency portals."""

    def __init__(self, base_url: str | None = None):
        """
        Args:
            base_url: URL of the maintenance transparency page.
                     If None, operates in local-file mode only.
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def scrape_from_url(self, url: str | None = None) -> list[dict]:
        """
        Scrape maintenance events from a live URL.

        Args:
            url: URL to scrape. Defaults to self.base_url.

        Returns:
            List of maintenance event dicts.

        Raises:
            ScraperError: On HTTP errors after retries exhausted.
        """
        target_url = url or self.base_url
        if not target_url:
            raise ScraperError("No URL configured for scraping")

        html = self._fetch_with_retry(target_url)
        return self.parse_html(html, source_url=target_url)

    def scrape_from_file(self, filepath: str | Path) -> list[dict]:
        """
        Parse maintenance events from a local HTML file (dev/test mode).

        Args:
            filepath: Path to the HTML file.

        Returns:
            List of maintenance event dicts.
        """
        filepath = Path(filepath)
        html = filepath.read_text(encoding="utf-8")
        return self.parse_html(html, source_url=f"file://{filepath}")

    def parse_html(self, html: str, source_url: str = "") -> list[dict]:
        """
        Parse maintenance events from raw HTML using parsel selectors.

        This method demonstrates C8 competency: structured data extraction
        from HTML using CSS selectors and XPath.

        Args:
            html: Raw HTML content.
            source_url: Source URL for provenance tracking.

        Returns:
            List of structured maintenance event dicts.
        """
        sel = Selector(text=html)
        events = []
        scraped_at = datetime.now(timezone.utc).isoformat()

        # CSS selector approach — target table rows with event data
        rows = sel.css("tr.event-row")

        for row in rows:
            event = {
                "event_id": row.css("td.event-id::text").get("").strip(),
                "unit_name": row.css("td.unit-name::text").get("").strip(),
                "affected_area": row.css("td.area::text").get("").strip(),
                "event_type": row.css("td.event-type::text").get("").strip(),
                "start_date": row.css("td.start-date::text").get("").strip(),
                "end_date": row.css("td.end-date::text").get("").strip(),
                "unavailable_mw": self._parse_mw(
                    row.css("td.unavail-mw::text").get("0")
                ),
                "description": row.css("td.description::text").get("").strip(),
                "source_url": source_url,
                "scraped_at": scraped_at,
            }

            # Also demonstrate XPath (C8 — dual approach)
            event_id_xpath = row.xpath(
                "./@data-event-id"
            ).get("")
            if event_id_xpath and not event["event_id"]:
                event["event_id"] = event_id_xpath

            if event["event_id"]:
                events.append(event)

        logger.info(
            "Parsed %d maintenance events from %s",
            len(events),
            source_url or "HTML content",
        )
        return events

    def _parse_mw(self, value: str) -> float:
        """Parse MW value from text, handling commas and whitespace."""
        try:
            return float(value.strip().replace(",", ".").replace(" ", ""))
        except (ValueError, AttributeError):
            return 0.0

    def _fetch_with_retry(self, url: str) -> str:
        """Fetch URL with exponential backoff and politeness delay."""
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Politeness delay
                if attempt > 0:
                    time.sleep(POLITENESS_DELAY)

                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    return response.text

                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = ScraperError(
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                    if attempt < MAX_RETRIES:
                        delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            "Retryable %d, attempt %d/%d, retry in %.1fs",
                            response.status_code,
                            attempt + 1,
                            MAX_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    break

                raise ScraperError(
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            except requests.exceptions.RequestException as e:
                last_error = ScraperError(f"Request failed: {e}")
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Request error, attempt %d/%d, retry in %.1fs",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    continue

        raise ScraperError(
            f"Max retries ({MAX_RETRIES}) exhausted. Last error: {last_error}"
        )
