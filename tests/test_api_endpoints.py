"""
Tests for the dataviz API (api/) — production/export endpoints.

Covers: error_handlers, models (query parsing), production_service,
export_service, and end-to-end FastAPI integration via TestClient.
"""

import csv
import io
import json
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from api.error_handlers import (
    bad_request,
    not_found,
    server_error,
    error_response,
)
from api.models import (
    parse_production_request,
    parse_export_request,
    ProductionResponse,
)
from api.production_service import (
    build_production_query,
    query_production,
    _aggregate_rows,
)
from api.export_service import (
    export_to_csv,
    _format_cell,
    UTF8_BOM,
    CSV_DELIMITER,
)
from functions.shared.gold.dim_loader import DimLoader
from functions.shared.gold.fact_loader import FactLoader


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite with Gold Star Schema + sample data."""
    # check_same_thread=False: FastAPI TestClient runs handlers in a worker thread.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    dim = DimLoader(conn)
    dim.ensure_schema()
    dim.upsert_sources()
    dim.upsert_regions([
        {"code_insee": "11", "nom_region": "Île-de-France"},
        {"code_insee": "84", "nom_region": "Auvergne-Rhône-Alpes"},
    ])
    dim.upsert_time([
        "2025-06-15T10:00:00+00:00",
        "2025-06-15T10:15:00+00:00",
        "2025-06-15T10:30:00+00:00",
    ])

    cursor = conn.cursor()
    # Insert 6 fact rows: 2 regions × 3 timestamps, source=eolien (id_source=2)
    # DimLoader upsert_sources creates: nucleaire=1, eolien=2, solaire=3 …
    # Region 1 (Île-de-France): consommation_mw set; Region 2 (ARA): NULL
    for id_date in [1, 2, 3]:
        for id_region, mw in [(1, 450.0), (2, 280.0)]:
            consommation = round(mw * 1.1, 2) if id_region == 1 else None
            cursor.execute(
                """INSERT INTO FACT_ENERGY_FLOW
                   (id_date, id_region, id_source, valeur_mw, facteur_charge, consommation_mw)
                   VALUES (?, ?, 2, ?, ?, ?)""",
                (id_date, id_region, mw, round(mw / 5000, 4), consommation),
            )
    conn.commit()
    return conn


# ─── Error handlers ───────────────────────────────────────────────────────────

class TestErrorHandlers:
    def test_bad_request_structure(self):
        resp = bad_request("invalid param", request_id="abc")
        assert resp["status_code"] == 400
        assert resp["error"] == "Bad Request"
        assert resp["request_id"] == "abc"
        assert "invalid param" in resp["message"]

    def test_not_found_structure(self):
        resp = not_found(request_id="y")
        assert resp["status_code"] == 404
        assert resp["error"] == "Not Found"

    def test_server_error_structure(self):
        resp = server_error(request_id="z")
        assert resp["status_code"] == 500
        assert resp["error"] == "Internal Server Error"

    def test_auto_request_id(self):
        """request_id always present even when not supplied."""
        resp = error_response(400, "test")
        assert uuid.UUID(resp["request_id"])  # valid UUID

    def test_details_default_empty_dict(self):
        resp = bad_request("msg")
        assert resp["details"] == {}

    def test_custom_details(self):
        resp = error_response(400, "msg", details={"field": "region_code"})
        assert resp["details"]["field"] == "region_code"


# ─── Models / parameter parsing ───────────────────────────────────────────────

class TestModels:
    def test_parse_production_defaults(self):
        req, err = parse_production_request({})
        assert err is None
        assert req.limit == 100
        assert req.offset == 0
        assert req.region_code is None

    def test_parse_production_all_params(self):
        req, err = parse_production_request({
            "region_code": "11",
            "start_date": "2025-06-01T00:00:00",
            "end_date": "2025-06-30T23:59:59",
            "source_type": "eolien",
            "limit": "50",
            "offset": "10",
        })
        assert err is None
        assert req.region_code == "11"
        assert req.limit == 50
        assert req.offset == 10

    def test_parse_production_invalid_limit(self):
        _, err = parse_production_request({"limit": "abc"})
        assert err is not None
        assert "integer" in err

    def test_parse_production_limit_out_of_range(self):
        _, err = parse_production_request({"limit": "5000"})
        assert err is not None
        assert "1000" in err

    def test_parse_production_negative_offset(self):
        _, err = parse_production_request({"offset": "-1"})
        assert err is not None

    def test_parse_export_request(self):
        req = parse_export_request({"region_code": "84"})
        assert req.region_code == "84"
        assert req.start_date is None

    def test_production_response_to_dict(self):
        resp = ProductionResponse(
            request_id="rid", total_records=2, limit=100, offset=0,
            data=[{"a": 1}],
        )
        d = resp.to_dict()
        assert d["request_id"] == "rid"
        assert d["total_records"] == 2
        assert len(d["data"]) == 1


# ─── production_service unit tests ────────────────────────────────────────────

class TestProductionService:
    def test_build_query_no_filters_sqlite(self):
        sql, params = build_production_query(is_sqlite=True)
        assert "FACT_ENERGY_FLOW" in sql
        assert "LIMIT ?" in sql
        assert "OFFSET ?" not in sql
        assert "consommation_mw" in sql
        # No date bounds -> falls back to the fixed MAX_SQL_LIMIT cap
        assert params[-1] == 700_000

    def test_build_query_no_filters_postgres(self):
        sql, params = build_production_query(is_sqlite=False)
        assert "fact_energy_flow" in sql
        assert "LIMIT" in sql
        assert "consommation_mw" in sql
        # sql_limit is last param for LIMIT %s
        assert params[-1] == 700_000

    def test_build_query_with_region(self):
        sql, params = build_production_query(region_code="11", is_sqlite=True)
        assert "r.code_insee = ?" in sql
        assert "11" in params

    def test_build_query_with_all_filters(self):
        sql, params = build_production_query(
            region_code="11",
            start_date="2025-06-01",
            end_date="2025-06-30",
            source_type="eolien",
            limit=50,
            offset=10,
            is_sqlite=True,
        )
        assert params.count("11") == 1
        assert "2025-06-01" in params
        # Date-only end_date must be expanded to include full day
        assert "2025-06-30 23:59:59" in params
        assert "eolien" in params
        # 30-day span -> sql_limit sized to cover the whole range
        # (30 days * 12 regions * 9 sources * 96 slots/day = 311_040),
        # not just (offset=10 + limit=50) * 10 = 600. No OFFSET in SQL params.
        assert params[-1] == 311_040

    def test_build_query_end_date_only_expanded(self):
        """Date-only end_date (YYYY-MM-DD) must be expanded to 23:59:59."""
        _, params = build_production_query(end_date="2025-06-30", is_sqlite=True)
        assert "2025-06-30 23:59:59" in params

    def test_build_query_end_date_datetime_unchanged(self):
        """Datetime end_date (with time) must not be modified."""
        _, params = build_production_query(end_date="2025-06-30T18:00:00", is_sqlite=True)
        assert "2025-06-30T18:00:00" in params

    def test_aggregate_rows_pivot(self):
        """sources dict is correctly built from flat rows."""
        cols = ["code_insee", "nom_region", "horodatage", "source_name", "valeur_mw", "facteur_charge", "consommation_mw"]
        rows = [
            ("11", "IDF", "2025-06-15T10:00", "eolien", 450.0, 0.09, 500.0),
            ("11", "IDF", "2025-06-15T10:00", "solaire", 320.0, 0.06, 500.0),
        ]
        data = _aggregate_rows(rows, cols)
        assert len(data) == 1
        record = data[0]
        assert record["code_insee"] == "11"
        assert record["sources"]["eolien"] == 450.0
        assert record["sources"]["solaire"] == 320.0

    def test_aggregate_rows_datetime_serializable(self):
        """pyodbc returns datetime objects — must be JSON serializable."""
        import json
        from datetime import datetime
        from decimal import Decimal
        cols = ["code_insee", "nom_region", "horodatage", "source_name", "valeur_mw", "facteur_charge", "consommation_mw"]
        rows = [
            ("11", "IDF", datetime(2025, 6, 15, 10, 0, 0), "eolien", Decimal("450.00"), Decimal("0.09"), Decimal("500.00")),
        ]
        data = _aggregate_rows(rows, cols)
        # Must not raise — all values must be JSON serializable
        serialized = json.dumps(data)
        reparsed = json.loads(serialized)
        assert reparsed[0]["sources"]["eolien"] == 450.0
        assert "2025-06-15" in reparsed[0]["timestamp"]
        assert reparsed[0]["consommation_mw"] == 500.0

    def test_query_production_returns_data(self, db):
        """Returns aggregated data from Gold SQL."""
        result = query_production(db, request_id="test-rid")
        assert result["request_id"] == "test-rid"
        assert result["total_records"] > 0
        record = result["data"][0]
        assert "code_insee" in record
        assert "sources" in record
        assert "timestamp" in record

    def test_query_production_filter_region(self, db):
        """region_code filter works."""
        result = query_production(db, region_code="11")
        assert result["total_records"] > 0
        for rec in result["data"]:
            assert rec["code_insee"] == "11"

    def test_query_production_empty_returns_empty_list(self, db):
        result = query_production(db, region_code="ZZ")
        assert result["total_records"] == 0
        assert result["data"] == []

    def test_query_production_pagination(self, db):
        all_data = query_production(db, limit=100, offset=0)
        page1 = query_production(db, limit=1, offset=0)
        page2 = query_production(db, limit=1, offset=1)
        # total_records = all aggregated non-zero records (consistent across pages)
        assert page1["total_records"] == all_data["total_records"]
        assert page2["total_records"] == all_data["total_records"]
        # Each page returns exactly 1 record
        assert len(page1["data"]) == 1
        assert len(page2["data"]) == 1
        assert page1["data"][0] != page2["data"][0]

    def test_query_production_response_envelope(self, db):
        result = query_production(db, limit=5, offset=0)
        assert "request_id" in result
        assert "total_records" in result
        assert "limit" in result
        assert result["limit"] == 5
        assert "offset" in result

    def test_query_production_includes_consommation_mw(self, db):
        """consommation_mw appears at region/timestamp level in each record."""
        result = query_production(db, request_id="cons-test")
        assert result["total_records"] > 0
        for record in result["data"]:
            assert "consommation_mw" in record

    def test_query_production_consommation_mw_value(self, db):
        """Region 1 (code_insee=11) has consommation_mw = round(450.0 * 1.1, 2) as set in fixture."""
        expected = round(450.0 * 1.1, 2)  # matches fixture: round(mw * 1.1, 2) for id_region=1
        result = query_production(db, region_code="11")
        assert result["total_records"] > 0
        for record in result["data"]:
            assert record["consommation_mw"] == pytest.approx(expected)

    def test_query_production_consommation_mw_null(self, db):
        """Region 2 (code_insee=84) has consommation_mw = NULL → null in JSON."""
        import json
        result = query_production(db, region_code="84")
        assert result["total_records"] > 0
        serialized = json.dumps(result)
        reparsed = json.loads(serialized)
        for record in reparsed["data"]:
            assert "consommation_mw" in record
            assert record["consommation_mw"] is None


# ─── export_service unit tests ────────────────────────────────────────────────

class TestExportService:
    def test_format_cell_none(self):
        assert _format_cell(None) == ""

    def test_format_cell_float_comma(self):
        """FR locale — decimal comma."""
        val = _format_cell(0.0945)
        assert "," in val
        assert "." not in val

    def test_format_cell_string(self):
        assert _format_cell("Île-de-France") == "Île-de-France"

    def test_export_returns_bom(self, db):
        """UTF-8 BOM for Excel compatibility."""
        csv_bytes, _, _ = export_to_csv(db, request_id="test-exp")
        assert csv_bytes[:3] == UTF8_BOM

    def test_export_semicolon_delimiter(self, db):
        """Semicolon separator for FR Excel."""
        csv_bytes, _, _ = export_to_csv(db)
        content = csv_bytes.decode("utf-8-sig")   # strip BOM
        lines = content.strip().splitlines()
        assert CSV_DELIMITER in lines[0]

    def test_export_has_header_row(self, db):
        csv_bytes, _, _ = export_to_csv(db)
        content = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content), delimiter=CSV_DELIMITER)
        rows = list(reader)
        assert len(rows) >= 2  # header + at least one data row

    def test_export_filename_format(self, db):
        _, filename, _ = export_to_csv(db, request_id="abc12345xyz")
        assert filename.endswith(".csv")
        assert "production_energie" in filename
        assert "abc12345" in filename

    def test_export_filename_with_region(self, db):
        _, filename, _ = export_to_csv(db, region_code="11", request_id="abc12345")
        assert "_11_" in filename

    def test_export_filter_region(self, db):
        csv_bytes_all, _, _ = export_to_csv(db)
        csv_bytes_region, _, _ = export_to_csv(db, region_code="11")
        # Region-filtered CSV should be smaller
        assert len(csv_bytes_region) < len(csv_bytes_all)

    def test_export_empty_result(self, db):
        csv_bytes, _, row_count = export_to_csv(db, region_code="ZZ")
        assert row_count == 0
        content = csv_bytes.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=CSV_DELIMITER))
        # Only header row, no data
        assert len(rows) == 1


# ─── FastAPI integration ──────────────────────────────────────────────────────

@pytest.fixture
def client(db, monkeypatch):
    """TestClient with api.main.get_db_connection patched to the sqlite fixture."""
    import api.main as main_module

    monkeypatch.setattr(main_module, "get_db_connection", lambda: db)
    return TestClient(main_module.app)


class TestHTTPIntegration:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_production_200_with_data(self, client):
        resp = client.get("/v1/production/regional")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["total_records"] > 0

    def test_production_200_json_structure(self, client):
        resp = client.get("/v1/production/regional", params={"request_id_unused": 1})
        body = resp.json()
        assert "request_id" in body
        assert "limit" in body
        assert "offset" in body
        for rec in body["data"]:
            assert "code_insee" in rec
            assert "region" in rec
            assert "timestamp" in rec
            assert "sources" in rec
            assert "consommation_mw" in rec

    def test_production_400_invalid_limit(self, client):
        resp = client.get("/v1/production/regional", params={"limit": "not_a_number"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["status_code"] == 400
        assert "request_id" in body

    def test_production_400_limit_too_high(self, client):
        resp = client.get("/v1/production/regional", params={"limit": "9999"})
        assert resp.status_code == 400

    def test_production_404_no_data(self, client):
        resp = client.get("/v1/production/regional", params={"region_code": "ZZ"})
        assert resp.status_code == 404
        assert resp.json()["status_code"] == 404

    def test_production_request_id_in_header(self, client):
        resp = client.get("/v1/production/regional")
        assert "X-Request-Id" in resp.headers

    def test_production_filter_by_region(self, client):
        resp = client.get("/v1/production/regional", params={"region_code": "11"})
        assert resp.status_code == 200
        for rec in resp.json()["data"]:
            assert rec["code_insee"] == "11"

    def test_export_200_with_data(self, client):
        resp = client.get("/v1/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    def test_export_content_disposition_header(self, client):
        resp = client.get("/v1/export/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".csv" in resp.headers.get("content-disposition", "")

    def test_export_utf8_bom(self, client):
        resp = client.get("/v1/export/csv")
        assert resp.status_code == 200
        assert resp.content[:3] == UTF8_BOM

    def test_export_404_no_data(self, client):
        resp = client.get("/v1/export/csv", params={"region_code": "ZZ"})
        assert resp.status_code == 404

    def test_meteo_endpoint(self, client):
        resp = client.get("/v1/meteo/regional")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_capacity_endpoint(self, client):
        resp = client.get("/v1/capacity/regional")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_maintenance_endpoint(self, client):
        resp = client.get("/v1/maintenance")
        assert resp.status_code == 200
        assert "data" in resp.json()


# ─── Performance — <500ms on sample dataset ───────────────────────────────────

class TestPerformance:
    """Response time budget for the dataviz endpoints."""

    def test_production_query_under_500ms(self, db):
        """Baseline: <500ms on SQLite in-memory with small dataset."""
        start = time.perf_counter()
        query_production(db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Query took {elapsed_ms:.1f}ms — exceeds 500ms budget"

    def test_export_csv_under_500ms(self, db):
        start = time.perf_counter()
        export_to_csv(db)  # returns (bytes, filename, row_count)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"CSV export took {elapsed_ms:.1f}ms — exceeds 500ms budget"

    def test_production_filtered_query_under_500ms(self, db):
        start = time.perf_counter()
        query_production(db, region_code="11", limit=50)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Filtered query took {elapsed_ms:.1f}ms"
