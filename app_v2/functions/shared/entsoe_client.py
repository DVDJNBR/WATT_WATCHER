"""
ENTSO-E Transparency Platform Client — day-ahead electricity prices for France.

Fetches document type A44 (Price Document) for the French bidding zone. France
is a single national market ("single bidding zone" per ACER's Bidding Zone
Review), so this returns one national price series — never per-region.

Requires a free API token: register at https://transparency.entsoe.eu/, then
email transparency@entsoe.eu with subject "RESTful API access" and your
registered email address in the body (granted within ~3 working days, no
justification required). Passed here as ENTSOE_API_TOKEN.

Resolution changed European-wide from hourly (PT60M) to 15-minute (PT15M)
market time units on 2025-10-01 (SDAC MTU transition) — this client handles
both transparently.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://web-api.tp.entsoe.eu/api"
FRANCE_DOMAIN = "10YFR-RTE------C"  # single national bidding zone (EIC code)
DOCUMENT_TYPE_DAY_AHEAD_PRICES = "A44"
REQUEST_TIMEOUT = 30

# ENTSO-E's IEC 62325 namespace — the exact URI is stable across document
# types/versions in practice but pinned here rather than wildcarded, since a
# silent namespace mismatch would make every find() below return None.
_NS = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}

_RESOLUTION_STEP = {
    "PT60M": timedelta(hours=1),
    "PT30M": timedelta(minutes=30),
    "PT15M": timedelta(minutes=15),
}


class EntsoeClientError(Exception):
    """Raised on ENTSO-E API errors: missing token, HTTP failure, or a
    rejected request (Acknowledgement_MarketDocument instead of price data)."""


class EntsoeClient:
    """Client for ENTSO-E's day-ahead price API, scoped to France."""

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token
        self.session = requests.Session()

    def fetch_day_ahead_prices(
        self, period_start: datetime, period_end: datetime
    ) -> list[dict]:
        """
        Fetch day-ahead prices for France in [period_start, period_end) (UTC).

        Returns:
            List of {"timestamp": datetime (UTC), "price_eur_mwh": float},
            one entry per market time unit actually published in the range.

        Raises:
            EntsoeClientError: missing token, HTTP failure, or a request
                ENTSO-E itself rejected (e.g. no data published yet for
                part of the range).
        """
        if not self.api_token:
            raise EntsoeClientError("ENTSOE_API_TOKEN not configured")

        params = {
            "securityToken": self.api_token,
            "documentType": DOCUMENT_TYPE_DAY_AHEAD_PRICES,
            "in_Domain": FRANCE_DOMAIN,
            "out_Domain": FRANCE_DOMAIN,
            "periodStart": period_start.strftime("%Y%m%d%H%M"),
            "periodEnd": period_end.strftime("%Y%m%d%H%M"),
        }

        try:
            response = self.session.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise EntsoeClientError(f"Request failed: {exc}") from exc

        if response.status_code == 401:
            raise EntsoeClientError("Invalid or missing ENTSO-E security token")
        if response.status_code != 200:
            raise EntsoeClientError(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )

        return self._parse_price_document(response.text)

    @staticmethod
    def _parse_price_document(xml_text: str) -> list[dict]:
        """Parse an A44 Publication_MarketDocument into flat price records."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise EntsoeClientError(f"Malformed XML response: {exc}") from exc

        # A rejected request (bad params, nothing published yet for the range,
        # quota, ...) comes back as an Acknowledgement_MarketDocument with a
        # 200 status — no TimeSeries to find, so surface the real reason
        # instead of silently returning an empty list.
        if root.tag.endswith("Acknowledgement_MarketDocument"):
            reason = root.findtext(".//{*}Reason/{*}text") or "no reason given"
            raise EntsoeClientError(f"ENTSO-E rejected the request: {reason}")

        records: list[dict] = []
        for period in root.findall(".//ns:TimeSeries/ns:Period", _NS):
            start_str = period.findtext("ns:timeInterval/ns:start", namespaces=_NS)
            resolution = period.findtext("ns:resolution", namespaces=_NS)
            step = _RESOLUTION_STEP.get(resolution or "")
            if not start_str or step is None:
                logger.warning(
                    "Skipping Period with unhandled resolution %r", resolution
                )
                continue

            period_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=timezone.utc
            )

            for point in period.findall("ns:Point", _NS):
                position_str = point.findtext("ns:position", namespaces=_NS)
                price_str = point.findtext("ns:price.amount", namespaces=_NS)
                if position_str is None or price_str is None:
                    continue
                position = int(position_str)
                ts = period_start + step * (position - 1)
                records.append({"timestamp": ts, "price_eur_mwh": float(price_str)})

        logger.info("Parsed %d price points from ENTSO-E response", len(records))
        return records
