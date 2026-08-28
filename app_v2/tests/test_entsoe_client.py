"""Tests for entsoe_client.py — FT/PRICES."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import io
import zipfile

import pytest

from functions.shared.entsoe_client import EntsoeClient, EntsoeClientError

NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
OUTAGE_NS = "urn:iec62325.351:tc57wg16:451-1:outagedocument:4:0"


def _outage_document(business_type, resource_mrid, resource_name, nominal_p,
                      period_start, period_end, quantities):
    points_xml = "".join(
        f"<Point><position>{i + 1}</position><quantity>{q}</quantity></Point>"
        for i, q in enumerate(quantities)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Unavailability_MarketDocument xmlns="{OUTAGE_NS}">
  <mRID>test-outage</mRID>
  <TimeSeries>
    <mRID>1</mRID>
    <businessType>{business_type}</businessType>
    <production_RegisteredResource.mRID codingScheme="A01">{resource_mrid}</production_RegisteredResource.mRID>
    <production_RegisteredResource.name>{resource_name}</production_RegisteredResource.name>
    <production_RegisteredResource.pSRType.powerSystemResources.nominalP>{nominal_p}</production_RegisteredResource.pSRType.powerSystemResources.nominalP>
    <Available_Period>
      <timeInterval><start>{period_start}</start><end>{period_end}</end></timeInterval>
      <resolution>PT60M</resolution>
      {points_xml}
    </Available_Period>
  </TimeSeries>
</Unavailability_MarketDocument>"""


def _zip_of(*xml_docs: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i, doc in enumerate(xml_docs):
            zf.writestr(f"doc_{i}.xml", doc)
    return buf.getvalue()


def _price_document(period_start: str, resolution: str, points: list[tuple[int, float]]) -> str:
    """Build a minimal but valid A44 Publication_MarketDocument."""
    points_xml = "".join(
        f"<Point><position>{pos}</position><price.amount>{price}</price.amount></Point>"
        for pos, price in points
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Publication_MarketDocument xmlns="{NS}">
  <mRID>test</mRID>
  <type>A44</type>
  <TimeSeries>
    <mRID>1</mRID>
    <in_Domain.mRID codingScheme="A01">10YFR-RTE------C</in_Domain.mRID>
    <out_Domain.mRID codingScheme="A01">10YFR-RTE------C</out_Domain.mRID>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <Period>
      <timeInterval><start>{period_start}</start></timeInterval>
      <resolution>{resolution}</resolution>
      {points_xml}
    </Period>
  </TimeSeries>
</Publication_MarketDocument>"""


def _acknowledgement(reason: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Acknowledgement_MarketDocument xmlns="{NS}">
  <mRID>test</mRID>
  <Reason><code>999</code><text>{reason}</text></Reason>
</Acknowledgement_MarketDocument>"""


@pytest.fixture
def client():
    return EntsoeClient(api_token="test-token")


class TestFetchDayAheadPrices:
    def test_missing_token_raises(self):
        client = EntsoeClient(api_token=None)
        with pytest.raises(EntsoeClientError, match="not configured"):
            client.fetch_day_ahead_prices(
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

    def test_hourly_resolution(self, client):
        """PT60M (pre-2025-10-01): position N -> start + (N-1) hours."""
        xml = _price_document(
            "2025-01-01T00:00Z", "PT60M", [(1, 45.0), (2, -3.2), (3, 50.5)]
        )
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_day_ahead_prices(
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

        assert len(records) == 3
        assert records[0]["timestamp"] == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        assert records[0]["price_eur_mwh"] == 45.0
        assert records[1]["timestamp"] == datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
        assert records[1]["price_eur_mwh"] == -3.2
        assert records[2]["timestamp"] == datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc)

    def test_15min_resolution(self, client):
        """PT15M (post-2025-10-01 SDAC MTU transition): position N -> start + (N-1)*15min."""
        xml = _price_document(
            "2025-10-01T00:00Z", "PT15M", [(1, 10.0), (5, 20.0), (96, 30.0)]
        )
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_day_ahead_prices(
                datetime(2025, 10, 1, tzinfo=timezone.utc),
                datetime(2025, 10, 2, tzinfo=timezone.utc),
            )

        assert len(records) == 3
        assert records[0]["timestamp"] == datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc)
        # position 5 -> 4 * 15min = 1h after period start
        assert records[1]["timestamp"] == datetime(2025, 10, 1, 1, 0, tzinfo=timezone.utc)
        # position 96 -> 95 * 15min = 23h45 after period start
        assert records[2]["timestamp"] == datetime(2025, 10, 1, 23, 45, tzinfo=timezone.utc)

    def test_negative_prices_parsed_correctly(self, client):
        """Negative prices are the whole point of this integration — must round-trip exactly."""
        xml = _price_document("2025-04-05T00:00Z", "PT60M", [(13, -115.46)])
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_day_ahead_prices(
                datetime(2025, 4, 5, tzinfo=timezone.utc),
                datetime(2025, 4, 6, tzinfo=timezone.utc),
            )

        assert records[0]["price_eur_mwh"] == -115.46

    def test_acknowledgement_document_raises_with_reason(self, client):
        """A rejected request comes back as 200 + Acknowledgement, not an error status."""
        xml = _acknowledgement("No matching data found for Data item Publication_MarketDocument.")
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(EntsoeClientError, match="No matching data found"):
                client.fetch_day_ahead_prices(
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                )

    def test_401_raises_auth_error(self, client):
        mock_resp = MagicMock(status_code=401, text="Unauthorized")
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(EntsoeClientError, match="Invalid or missing"):
                client.fetch_day_ahead_prices(
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                )

    def test_other_http_error_raises(self, client):
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(EntsoeClientError, match="HTTP 500"):
                client.fetch_day_ahead_prices(
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                )

    def test_malformed_xml_raises(self, client):
        mock_resp = MagicMock(status_code=200, text="<not><valid")
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(EntsoeClientError, match="Malformed XML"):
                client.fetch_day_ahead_prices(
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                )

    def test_unknown_resolution_skipped_not_raised(self, client):
        """An unexpected resolution (e.g. future PT5M) is skipped, not fatal."""
        xml = _price_document("2025-01-01T00:00Z", "PT5M", [(1, 10.0)])
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_day_ahead_prices(
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

        assert records == []

    def test_request_params(self, client):
        """Sanity check on the exact params sent — France single bidding zone, A44."""
        xml = _price_document("2025-01-01T00:00Z", "PT60M", [(1, 10.0)])
        mock_resp = MagicMock(status_code=200, text=xml)

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.fetch_day_ahead_prices(
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
            )

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["securityToken"] == "test-token"
        assert params["documentType"] == "A44"
        assert params["in_Domain"] == "10YFR-RTE------C"
        assert params["out_Domain"] == "10YFR-RTE------C"
        assert params["periodStart"] == "202501010000"
        assert params["periodEnd"] == "202501020000"


class TestFetchUnavailabilityOfProductionUnits:
    def test_missing_token_raises(self):
        client = EntsoeClient(api_token=None)
        with pytest.raises(EntsoeClientError, match="not configured"):
            client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )

    def test_parses_zip_of_one_outage(self, client):
        xml = _outage_document(
            "A54", "10T-GRAVELINES3", "GRAVELINES 3", 900.0,
            "2026-09-01T06:00Z", "2026-09-15T18:00Z", [0.0],
        )
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml), headers={"Content-Type": "application/zip"})

        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 16, tzinfo=timezone.utc),
            )

        assert len(records) == 1
        r = records[0]
        assert r["unit_name"] == "GRAVELINES 3"
        assert r["event_type"] == "unplanned"
        assert r["unavailable_mw"] == 900.0
        assert r["start_date"] == datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)
        assert r["end_date"] == datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)

    def test_planned_business_type(self):
        client = EntsoeClient(api_token="t")
        xml = _outage_document(
            "A53", "10T-X", "SITE X", 500.0, "2026-01-01T00:00Z", "2026-01-02T00:00Z", [250.0],
        )
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml), headers={"Content-Type": "application/zip"})
        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
        assert records[0]["event_type"] == "planned"
        assert records[0]["unavailable_mw"] == 250.0

    def test_zero_reduction_skipped(self):
        """A record where available == nominal (no real outage) shouldn't surface."""
        client = EntsoeClient(api_token="t")
        xml = _outage_document(
            "A54", "10T-X", "SITE X", 500.0, "2026-01-01T00:00Z", "2026-01-02T00:00Z", [500.0],
        )
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml), headers={"Content-Type": "application/zip"})
        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
        assert records == []

    def test_worst_case_within_period(self):
        """Multiple points in one period: unavailable_mw uses the minimum
        available quantity (worst-case reduction), not the first point."""
        client = EntsoeClient(api_token="t")
        xml = _outage_document(
            "A54", "10T-X", "SITE X", 1000.0, "2026-01-01T00:00Z", "2026-01-01T03:00Z",
            [800.0, 200.0, 600.0],
        )
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml), headers={"Content-Type": "application/zip"})
        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        assert records[0]["unavailable_mw"] == 800.0  # 1000 - min(800,200,600)

    def test_multiple_documents_in_zip(self):
        client = EntsoeClient(api_token="t")
        xml1 = _outage_document("A54", "10T-A", "SITE A", 400.0, "2026-01-01T00:00Z", "2026-01-02T00:00Z", [0.0])
        xml2 = _outage_document("A53", "10T-B", "SITE B", 300.0, "2026-01-03T00:00Z", "2026-01-04T00:00Z", [0.0])
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml1, xml2), headers={"Content-Type": "application/zip"})
        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
        assert {r["unit_name"] for r in records} == {"SITE A", "SITE B"}

    def test_acknowledgement_returns_empty_not_error(self):
        """Nothing in range comes back as a small XML Acknowledgement, not a ZIP."""
        client = EntsoeClient(api_token="t")
        xml = f"""<?xml version="1.0"?>
<Acknowledgement_MarketDocument xmlns="{OUTAGE_NS}">
  <Reason><code>999</code><text>No matching data found</text></Reason>
</Acknowledgement_MarketDocument>"""
        mock_resp = MagicMock(status_code=200, content=xml.encode("utf-8"), text=xml, headers={"Content-Type": "text/xml"})
        with patch.object(client.session, "get", return_value=mock_resp):
            records = client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        assert records == []

    def test_request_params(self):
        client = EntsoeClient(api_token="test-token")
        xml = _outage_document("A54", "10T-X", "SITE X", 500.0, "2026-01-01T00:00Z", "2026-01-02T00:00Z", [0.0])
        mock_resp = MagicMock(status_code=200, content=_zip_of(xml), headers={"Content-Type": "application/zip"})
        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.fetch_unavailability_of_production_units(
                datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["documentType"] == "A77"
        assert params["biddingZone_Domain"] == "10YFR-RTE------C"
