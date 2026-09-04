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

import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://web-api.tp.entsoe.eu/api"
FRANCE_DOMAIN = "10YFR-RTE------C"  # single national bidding zone (EIC code)
DOCUMENT_TYPE_DAY_AHEAD_PRICES = "A44"
DOCUMENT_TYPE_UNAVAILABILITY_PRODUCTION = "A77"
DOCUMENT_TYPE_ACTUAL_GENERATION_PER_UNIT = "A73"
PROCESS_TYPE_REALISED = "A16"
BUSINESS_TYPE_LABELS = {"A53": "planned", "A54": "unplanned"}
REQUEST_TIMEOUT = 30

# ENTSO-E PSR (Power System Resource) type codes, EIC standard — used to
# label each unit's fuel/technology on the A73 generation-unit registry.
PSR_TYPE_LABELS = {
    "B01": "biomass", "B02": "fossil_brown_coal", "B03": "fossil_coal_gas",
    "B04": "fossil_gas", "B05": "fossil_hard_coal", "B06": "fossil_oil",
    "B07": "fossil_oil_shale", "B08": "fossil_peat", "B09": "geothermal",
    "B10": "hydro_pumped_storage", "B11": "hydro_run_of_river",
    "B12": "hydro_water_reservoir", "B13": "marine", "B14": "nuclear",
    "B15": "other_renewable", "B16": "solar", "B17": "waste",
    "B18": "wind_offshore", "B19": "wind_onshore", "B20": "other",
}

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

    def fetch_unavailability_of_production_units(
        self, period_start: datetime, period_end: datetime
    ) -> list[dict]:
        """
        Fetch generation unit outages (A77) for France in [period_start, period_end).

        Unlike the price endpoint, this one serves a ZIP file (one or more XML
        Unavailability_MarketDocuments inside, EU-wide regulatory reporting can
        be verbose) and is capped at 200 items per request by ENTSO-E.

        Returns:
            List of {"event_id", "unit_name", "event_type" ("planned"/
            "unplanned"/"unknown"), "start_date", "end_date" (datetime, UTC),
            "unavailable_mw"} — one entry per outage period found. Best-effort:
            entries this parser can't fully make sense of are skipped with a
            warning rather than raising, since a malformed single record
            shouldn't take down the whole outages fetch.

        Raises:
            EntsoeClientError: missing token, HTTP failure, or a request
                ENTSO-E itself rejected.
        """
        if not self.api_token:
            raise EntsoeClientError("ENTSOE_API_TOKEN not configured")

        base_params = {
            "securityToken": self.api_token,
            "documentType": DOCUMENT_TYPE_UNAVAILABILITY_PRODUCTION,
            "biddingZone_Domain": FRANCE_DOMAIN,
            "periodStart": period_start.strftime("%Y%m%d%H%M"),
            "periodEnd": period_end.strftime("%Y%m%d%H%M"),
        }

        # ENTSO-E caps this endpoint at 200 instances per request (unlike
        # prices, which never hit this). A wide-enough period_start/period_end
        # window routinely exceeds it, so fetch page by page until the
        # server's own reported total is covered rather than assuming one
        # request is ever enough.
        xml_documents: list[str] = []
        offset = 0
        total_expected: int | None = None
        while True:
            page_params = dict(base_params)
            if offset:
                page_params["offset"] = offset

            try:
                response = self.session.get(BASE_URL, params=page_params, timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException as exc:
                raise EntsoeClientError(f"Request failed: {exc}") from exc

            if response.status_code == 401:
                raise EntsoeClientError("Invalid or missing ENTSO-E security token")

            if response.status_code == 400:
                over_limit = self._parse_over_limit_count(response.text)
                if over_limit is not None and offset == 0:
                    total_expected = over_limit
                    logger.info(
                        "ENTSO-E outages: %d instances in range, paginating by 200", over_limit,
                    )
                    offset = 200
                    continue
                raise EntsoeClientError(f"HTTP 400: {response.text[:300]}")

            if response.status_code != 200:
                raise EntsoeClientError(f"HTTP {response.status_code}: {response.text[:200]}")

            content_type = response.headers.get("Content-Type", "")
            if "zip" in content_type or response.content[:2] == b"PK":
                xml_documents.extend(self._extract_zip_xml(response.content))
            else:
                # No outages in range (or the last, partial page) comes back
                # as a single small XML, not a ZIP.
                xml_documents.append(response.text)

            if total_expected is None or offset + 200 >= total_expected:
                break
            offset += 200

        records: list[dict] = []
        for xml_text in xml_documents:
            records.extend(self._parse_unavailability_document(xml_text))
        logger.info("Parsed %d outage records from ENTSO-E response", len(records))
        return records

    def fetch_generation_unit_registry(
        self, period_start: datetime, period_end: datetime
    ) -> list[dict]:
        """
        Fetch the roster of large (>100MW, EU transparency threshold) French
        production units via A73 "Actual generation per generation unit".

        Unlike fetch_unavailability_of_production_units(), this reports every
        unit that generated in the window *regardless* of outage status —
        it's the master list a map needs (named + typed units that exist),
        with A77 layered on top only to say which of them are currently down.
        A single day is enough to see the full roster (units report daily
        whether they're impacted by an outage or not); a wider period_start/
        period_end just re-confirms the same units, deduplicated below.

        ENTSO-E caps this endpoint's own window at 1 day per request (unlike
        outages, which allows a wide window but caps item *count*) — a
        multi-day request here is split into daily calls and merged rather
        than left to the caller to chunk.

        Returns:
            List of {"unit_mrid", "unit_name", "psr_type"} — one entry per
            distinct registered unit seen across the whole period.

        Raises:
            EntsoeClientError: missing token, HTTP failure, or a request
                ENTSO-E itself rejected.
        """
        if not self.api_token:
            raise EntsoeClientError("ENTSOE_API_TOKEN not configured")

        units: dict[str, dict] = {}
        day_start = period_start
        while day_start < period_end:
            day_end = min(day_start + timedelta(days=1), period_end)
            params = {
                "securityToken": self.api_token,
                "documentType": DOCUMENT_TYPE_ACTUAL_GENERATION_PER_UNIT,
                "processType": PROCESS_TYPE_REALISED,
                "in_Domain": FRANCE_DOMAIN,
                "periodStart": day_start.strftime("%Y%m%d%H%M"),
                "periodEnd": day_end.strftime("%Y%m%d%H%M"),
            }

            try:
                response = self.session.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException as exc:
                raise EntsoeClientError(f"Request failed: {exc}") from exc

            if response.status_code == 401:
                raise EntsoeClientError("Invalid or missing ENTSO-E security token")
            if response.status_code != 200:
                raise EntsoeClientError(f"HTTP {response.status_code}: {response.text[:200]}")

            for unit in self._parse_generation_unit_registry(response.text):
                units[unit["unit_mrid"]] = unit

            day_start = day_end

        return list(units.values())

    @staticmethod
    def _parse_generation_unit_registry(xml_text: str) -> list[dict]:
        """Parse an A73 GL_MarketDocument into deduplicated unit registry rows."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise EntsoeClientError(f"Malformed XML response: {exc}") from exc

        if root.tag.endswith("Acknowledgement_MarketDocument"):
            reason = root.findtext(".//{*}Reason/{*}text") or "no reason given"
            logger.info("ENTSO-E generation registry: %s", reason)
            return []

        units: dict[str, dict] = {}
        for ts in root.findall(".//{*}TimeSeries"):
            unit_mrid = ts.findtext(".//{*}MktPSRType/{*}PowerSystemResources/{*}mRID")
            unit_name = ts.findtext(".//{*}MktPSRType/{*}PowerSystemResources/{*}name")
            psr_type = ts.findtext(".//{*}MktPSRType/{*}psrType")
            if not unit_mrid or not unit_name:
                continue
            units[unit_mrid] = {
                "unit_mrid": unit_mrid,
                "unit_name": unit_name,
                "psr_type": PSR_TYPE_LABELS.get(psr_type or "", psr_type or "unknown"),
            }

        return list(units.values())

    @staticmethod
    def _parse_over_limit_count(xml_text: str) -> int | None:
        """
        Extract the real instance count from ENTSO-E's "exceeds the allowed
        maximum (200)" Acknowledgement, e.g. "The number of instances (676)
        exceeds the allowed maximum (200) for data item ...". Returns None
        for any other 400 (a genuine error, not a pagination signal).
        """
        match = re.search(r"number of instances \((\d+)\) exceeds", xml_text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_zip_xml(content: bytes) -> list[str]:
        """Unzip an ENTSO-E outages response into its individual XML documents."""
        xml_documents = []
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        xml_documents.append(zf.read(name).decode("utf-8"))
        except zipfile.BadZipFile as exc:
            raise EntsoeClientError(f"Malformed ZIP response: {exc}") from exc
        return xml_documents

    @staticmethod
    def _parse_unavailability_document(xml_text: str) -> list[dict]:
        """
        Parse an A77 Unavailability_MarketDocument into flat outage records.

        Namespace-agnostic on purpose (`{*}` wildcards): ENTSO-E's outage
        schema URI is a different, less-frequently-referenced one than the
        price schema, and a hardcoded mismatch would silently return nothing
        with no error — safer to match on local element names only here and
        rely on the None-checks/logging below to surface real structural
        surprises instead.
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise EntsoeClientError(f"Malformed XML response: {exc}") from exc

        if root.tag.endswith("Acknowledgement_MarketDocument"):
            reason = root.findtext(".//{*}Reason/{*}text") or "no reason given"
            logger.info("ENTSO-E outages: %s (likely just 'nothing in range')", reason)
            return []

        records: list[dict] = []
        for ts in root.findall(".//{*}TimeSeries"):
            business_type = ts.findtext("{*}businessType")
            event_type = BUSINESS_TYPE_LABELS.get(business_type or "", "unknown")

            resource_mrid = ts.findtext(".//{*}production_RegisteredResource.mRID")
            resource_name = ts.findtext(".//{*}production_RegisteredResource.name")
            nominal_p_str = ts.findtext(
                ".//{*}production_RegisteredResource.pSRType.powerSystemResources.nominalP"
            )
            if not resource_mrid or nominal_p_str is None:
                logger.warning("Skipping outage TimeSeries missing resource id/nominalP")
                continue
            nominal_p = float(nominal_p_str)

            for period in ts.findall(".//{*}Available_Period"):
                start_str = period.findtext("{*}timeInterval/{*}start")
                end_str = period.findtext("{*}timeInterval/{*}end")
                if not start_str or not end_str:
                    continue
                start = datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                end = datetime.strptime(end_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)

                quantities = [
                    float(q) for q in (
                        pt.findtext("{*}quantity") for pt in period.findall(".//{*}Point")
                    ) if q is not None
                ]
                if not quantities:
                    continue
                # Worst-case reduction within the period, in case available
                # capacity ramps rather than staying flat for the whole window.
                unavailable_mw = nominal_p - min(quantities)
                if unavailable_mw <= 0:
                    continue

                records.append({
                    "event_id": f"{resource_mrid}_{start_str}",
                    "unit_name": resource_name or resource_mrid,
                    "event_type": event_type,
                    "start_date": start,
                    "end_date": end,
                    "unavailable_mw": round(unavailable_mw, 1),
                })

        return records

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
