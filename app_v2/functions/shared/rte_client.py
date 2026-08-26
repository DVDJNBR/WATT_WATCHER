"""
RTE eCO2mix API Client — Story 1.1, Task 2

Fetches real-time regional energy production data from the
Opendatasoft v2.1 API. No authentication required (public API).

Usage:
    client = RTEClient()
    data = client.fetch_eco2mix_regional()
"""

import logging
import random
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────
BASE_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"
DATASET_REGIONAL = "eco2mix-regional-tr"

# Retry config (FR7, NFR-R1)
MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403}

DEFAULT_LIMIT = 100  # records per page (API max)
REQUEST_TIMEOUT = 30  # seconds


class RTEClientError(Exception):
    """Base exception for RTE API client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RTEClient:
    """Client for RTE eCO2mix Opendatasoft API."""

    def __init__(self, base_url: str = BASE_URL, dataset: str = DATASET_REGIONAL):
        self.base_url = base_url
        self.dataset = dataset
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "GRID_POWER_STREAM/1.0 DataIngestion"}
        )

    @property
    def records_url(self) -> str:
        return f"{self.base_url}/{self.dataset}/records"

    def fetch_eco2mix_regional(
        self,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        since: datetime | None = None,
        region_code: str | None = None,
    ) -> dict:
        """
        Fetch eco2mix regional records.

        Args:
            limit: Max records per request (max 100).
            offset: Pagination offset.
            since: Only records after this datetime.
            region_code: Filter by INSEE region code (e.g. '11' for IDF).

        Returns:
            Raw API response dict with 'total_count' and 'results'.

        Raises:
            RTEClientError: On API errors after retries exhausted.
        """
        params: dict = {"limit": min(limit, 100), "offset": offset}

        # Build ODSQL where clause
        where_clauses = []
        if since:
            iso = since.strftime("%Y-%m-%dT%H:%M:%S")
            where_clauses.append(f"date_heure >= '{iso}'")
        if region_code:
            where_clauses.append(f"code_insee_region = '{region_code}'")

        if where_clauses:
            params["where"] = " AND ".join(where_clauses)

        params["order_by"] = "date_heure DESC"

        return self._request_with_retry(params)

    def fetch_all_recent(self, minutes: int = 30) -> list[dict]:
        """
        Fetch all records from the last N minutes, handling pagination.

        Returns:
            List of all record dicts.
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        all_records = []
        offset = 0

        while True:
            response = self.fetch_eco2mix_regional(
                limit=100, offset=offset, since=since
            )
            records = response.get("results", [])
            all_records.extend(records)

            total = response.get("total_count", 0)
            offset += len(records)

            if not records or offset >= total:
                break

        logger.info(
            "Fetched %d records since %s", len(all_records), since.isoformat()
        )
        return all_records

    def _request_with_retry(self, params: dict) -> dict:
        """Execute GET with exponential backoff retry."""
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    self.records_url, params=params, timeout=REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    return response.json()

                # Non-retryable errors — fail immediately
                if response.status_code in NON_RETRYABLE_STATUS_CODES:
                    raise RTEClientError(
                        f"Non-retryable error: HTTP {response.status_code} — {response.text[:200]}",
                        status_code=response.status_code,
                    )

                # Retryable errors
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = RTEClientError(
                        f"HTTP {response.status_code}", status_code=response.status_code
                    )
                    if attempt < MAX_RETRIES:
                        delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            "Retryable error %d, attempt %d/%d, retrying in %.1fs",
                            response.status_code,
                            attempt + 1,
                            MAX_RETRIES,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    # Last attempt exhausted — will be caught by the final raise
                    break

                # Unexpected status code
                raise RTEClientError(
                    f"Unexpected HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            except requests.exceptions.Timeout:
                last_error = RTEClientError("Request timeout")
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Timeout, attempt %d/%d, retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    continue

            except requests.exceptions.ConnectionError as e:
                last_error = RTEClientError(f"Connection error: {e}")
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Connection error, attempt %d/%d, retrying in %.1fs",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    continue

        raise RTEClientError(
            f"Max retries ({MAX_RETRIES}) exhausted. Last error: {last_error}"
        )
