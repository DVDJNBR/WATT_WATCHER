"""
Tests for Story 4.1 — Production API Endpoints

Tasks: 5.1 (production_service), 5.2 (export_service),
       5.3 (integration / HTTP trigger), 5.4 (performance).
"""

import csv
import io
import json
import sqlite3
import time
import uuid
from unittest.mock import MagicMock

import pytest

from functions.shared.api.error_handlers import (
    bad_request,
    not_found,
    server_error,
    unauthorized,
    error_response,
)
from functions.shared.api.models import (
    parse_production_request,
    parse_export_request,
    ProductionResponse,
)
from functions.shared.api.production_service import (
    build_production_query,
    query_production,
    _aggregate_rows,
)
from functions.shared.api.export_service import (
    export_to_csv,
    _format_cell,
    UTF8_BOM,
    CSV_DELIMITER,
)
from functions.shared.api.routes import (
    PRODUCTION_REGIONAL,
    EXPORT_CSV,
    ROUTE_PRODUCTION,
    ROUTE_EXPORT,
)
from functions.shared.gold.dim_loader import DimLoader
from functions.shared.gold.fact_loader import FactLoader


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite with Gold Star Schema + sample data."""
    conn = sqlite3.connect(":memory:")
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
    for id_date in [1, 2, 3]:
        for id_region, mw in [(1, 450.0), (2, 280.0)]:
            cursor.execute(
                """INSERT INTO FACT_ENERGY_FLOW
                   (id_date, id_region, id_source, valeur_mw, facteur_charge)
                   VALUES (?, ?, 2, ?, ?)""",
                (id_date, id_region, mw, round(mw / 5000, 4)),
            )
    conn.commit()
    return conn


# ─── Task 4: Error handlers ──────────────────────────────────────────────────

class TestErrorHandlers:
    def test_bad_request_structure(self):
        resp = bad_request("invalid param", request_id="abc")
        assert resp["status_code"] == 400
        assert resp["error"] == "Bad Request"
        assert resp["request_id"] == "abc"
        assert "invalid param" in resp["message"]

    def test_unauthorized_structure(self):
        resp = unauthorized(request_id="x")
        assert resp["status_code"] == 401
        assert resp["error"] == "Unauthorized"
        assert resp["request_id"] == "x"

    def test_not_found_structure(self):
        resp = not_found(request_id="y")
        assert resp["status_code"] == 404
        assert resp["error"] == "Not Found"

    def test_server_error_structure(self):
        resp = server_error(request_id="z")
        assert resp["status_code"] == 500
        assert resp["error"] == "Internal Server Error"

    def test_auto_request_id(self):
        """AC #4: request_id always present even when not supplied."""
        resp = error_response(400, "test")
        assert uuid.UUID(resp["request_id"])  # valid UUID

    def test_details_default_empty_dict(self):
        resp = bad_request("msg")
        assert resp["details"] == {}

    def test_custom_details(self):
        resp = error_response(400, "msg", details={"field": "region_code"})
        assert resp["details"]["field"] == "region_code"


# ─── Task 1.3: Models / parameter parsing ────────────────────────────────────

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


# ─── Task 1.2: Routes ────────────────────────────────────────────────────────

class TestRoutes:
    def test_versioned_prefix(self):
        assert PRODUCTION_REGIONAL.startswith("/v1/")
        assert EXPORT_CSV.startswith("/v1/")

    def test_route_constants(self):
        assert ROUTE_PRODUCTION == "v1/production/regional"
        assert ROUTE_EXPORT == "v1/export/csv"


# ─── Task 5.1: production_service unit tests ─────────────────────────────────

class TestProductionService:
    def test_build_query_no_filters_sqlite(self):
        sql, params = build_production_query(is_sqlite=True)
        assert "FACT_ENERGY_FLOW" in sql
        assert "LIMIT ?" in sql
        assert "OFFSET ?" not in sql
        # sql_limit = (offset=0 + limit=100) * 10 = 1000
        assert params[-1] == 1000

    def test_build_query_no_filters_sqlserver(self):
        sql, params = build_production_query(is_sqlite=False)
        assert "FACT_ENERGY_FLOW" in sql
        assert "TOP(?)" in sql.replace(" ", "")
        assert "LIMIT" not in sql
        # sql_limit is first param for TOP(?)
        assert params[0] == 1000

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
        # sql_limit = (offset=10 + limit=50) * 10 = 600; no OFFSET in SQL params
        assert params[-1] == 600

    def test_build_query_end_date_only_expanded(self):
        """Date-only end_date (YYYY-MM-DD) must be expanded to 23:59:59."""
        _, params = build_production_query(end_date="2025-06-30", is_sqlite=True)
        assert "2025-06-30 23:59:59" in params

    def test_build_query_end_date_datetime_unchanged(self):
        """Datetime end_date (with time) must not be modified."""
        _, params = build_production_query(end_date="2025-06-30T18:00:00", is_sqlite=True)
        assert "2025-06-30T18:00:00" in params

    def test_aggregate_rows_pivot(self):
        """AC #3: sources dict is correctly built from flat rows."""
        cols = ["code_insee", "nom_region", "horodatage", "source_name", "valeur_mw", "facteur_charge"]
        rows = [
            ("11", "IDF", "2025-06-15T10:00", "eolien", 450.0, 0.09),
            ("11", "IDF", "2025-06-15T10:00", "solaire", 320.0, 0.06),
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
        cols = ["code_insee", "nom_region", "horodatage", "source_name", "valeur_mw", "facteur_charge"]
        rows = [
            ("11", "IDF", datetime(2025, 6, 15, 10, 0, 0), "eolien", Decimal("450.00"), Decimal("0.09")),
        ]
        data = _aggregate_rows(rows, cols)
        # Must not raise — all values must be JSON serializable
        serialized = json.dumps(data)
        reparsed = json.loads(serialized)
        assert reparsed[0]["sources"]["eolien"] == 450.0
        assert "2025-06-15" in reparsed[0]["timestamp"]

    def test_query_production_returns_data(self, db):
        """AC #1: Returns aggregated data from Gold SQL."""
        result = query_production(db, request_id="test-rid")
        assert result["request_id"] == "test-rid"
        assert result["total_records"] > 0
        record = result["data"][0]
        assert "code_insee" in record
        assert "sources" in record
        assert "timestamp" in record

    def test_query_production_filter_region(self, db):
        """AC #1: region_code filter works."""
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


# ─── Task 5.2: export_service unit tests ─────────────────────────────────────

class TestExportService:
    def test_format_cell_none(self):
        assert _format_cell(None) == ""

    def test_format_cell_float_comma(self):
        """AC #4: FR locale — decimal comma."""
        val = _format_cell(0.0945)
        assert "," in val
        assert "." not in val

    def test_format_cell_string(self):
        assert _format_cell("Île-de-France") == "Île-de-France"

    def test_export_returns_bom(self, db):
        """AC #4: UTF-8 BOM for Excel compatibility."""
        csv_bytes, _, _ = export_to_csv(db, request_id="test-exp")
        assert csv_bytes[:3] == UTF8_BOM

    def test_export_semicolon_delimiter(self, db):
        """AC #4: Semicolon separator for FR Excel."""
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


# ─── Task 5.3: Integration — HTTP trigger simulation ─────────────────────────

class MockHttpRequest:
    """Minimal mock for func.HttpRequest."""
    def __init__(self, params: dict | None = None, body: bytes = b""):
        self.params = params or {}
        self.method = "GET"
        self._body = body

    def get_json(self) -> dict:
        return json.loads(self._body) if self._body else {}


class MockHttpResponse:
    """Captured HTTP response for assertions."""
    def __init__(self, body, status_code: int = 200, mimetype: str = "", headers: dict | None = None):
        self._body = body
        self.status_code = status_code
        self.mimetype = mimetype
        self.headers = headers or {}

    def get_body(self) -> bytes:
        if isinstance(self._body, bytes):
            return self._body
        if isinstance(self._body, str):
            return self._body.encode("utf-8")
        return self._body


def _simulate_production_endpoint(
    conn,
    params: dict,
    request_id: str | None = None,
) -> MockHttpResponse:
    """
    Simulate the /v1/production/regional handler logic (pure, no azure.functions).
    This is the production handler decoupled for testability.
    """
    from functions.shared.api.models import parse_production_request
    from functions.shared.api.production_service import query_production
    from functions.shared.api.error_handlers import bad_request, not_found, server_error

    rid = request_id or str(uuid.uuid4())

    prod_req, err = parse_production_request(params)
    if err:
        return MockHttpResponse(
            body=json.dumps(bad_request(err, rid)),
            status_code=400,
            mimetype="application/json",
            headers={"X-Request-Id": rid},
        )

    try:
        result = query_production(
            conn,
            region_code=prod_req.region_code,
            start_date=prod_req.start_date,
            end_date=prod_req.end_date,
            source_type=prod_req.source_type,
            limit=prod_req.limit,
            offset=prod_req.offset,
            request_id=rid,
        )

        if not result["data"]:
            return MockHttpResponse(
                body=json.dumps(not_found(request_id=rid)),
                status_code=404,
                mimetype="application/json",
                headers={"X-Request-Id": rid},
            )

        return MockHttpResponse(
            body=json.dumps(result),
            status_code=200,
            mimetype="application/json",
            headers={"X-Request-Id": rid},
        )

    except Exception as exc:
        return MockHttpResponse(
            body=json.dumps(server_error(request_id=rid)),
            status_code=500,
            mimetype="application/json",
            headers={"X-Request-Id": rid},
        )


def _simulate_export_endpoint(
    conn,
    params: dict,
    request_id: str | None = None,
) -> MockHttpResponse:
    """Simulate the /v1/export/csv handler logic."""
    from functions.shared.api.models import parse_export_request
    from functions.shared.api.export_service import export_to_csv
    from functions.shared.api.error_handlers import not_found, server_error

    rid = request_id or str(uuid.uuid4())
    export_req = parse_export_request(params)

    try:
        csv_bytes, filename, row_count = export_to_csv(
            conn,
            region_code=export_req.region_code,
            start_date=export_req.start_date,
            end_date=export_req.end_date,
            source_type=export_req.source_type,
            request_id=rid,
        )

        if row_count == 0:
            return MockHttpResponse(
                body=json.dumps(not_found(request_id=rid)),
                status_code=404,
                mimetype="application/json",
                headers={"X-Request-Id": rid},
            )

        return MockHttpResponse(
            body=csv_bytes,
            status_code=200,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Request-Id": rid,
            },
        )

    except Exception:
        return MockHttpResponse(
            body=json.dumps(server_error(request_id=rid)),
            status_code=500,
            mimetype="application/json",
            headers={"X-Request-Id": rid},
        )


class TestHTTPIntegration:
    """AC #3: HTTP trigger → response validation."""

    def test_production_200_with_data(self, db):
        resp = _simulate_production_endpoint(db, {})
        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert "data" in body
        assert body["total_records"] > 0

    def test_production_200_json_structure(self, db):
        resp = _simulate_production_endpoint(db, {}, request_id="int-test")
        body = json.loads(resp.get_body())
        assert body["request_id"] == "int-test"
        assert "limit" in body
        assert "offset" in body
        # Each record must have required fields
        for rec in body["data"]:
            assert "code_insee" in rec
            assert "region" in rec
            assert "timestamp" in rec
            assert "sources" in rec

    def test_production_400_invalid_limit(self, db):
        resp = _simulate_production_endpoint(db, {"limit": "not_a_number"})
        assert resp.status_code == 400
        body = json.loads(resp.get_body())
        assert body["status_code"] == 400
        assert "request_id" in body

    def test_production_400_limit_too_high(self, db):
        resp = _simulate_production_endpoint(db, {"limit": "9999"})
        assert resp.status_code == 400

    def test_production_404_no_data(self, db):
        resp = _simulate_production_endpoint(db, {"region_code": "ZZ"})
        assert resp.status_code == 404
        body = json.loads(resp.get_body())
        assert body["status_code"] == 404

    def test_production_request_id_in_header(self, db):
        resp = _simulate_production_endpoint(db, {}, request_id="my-rid")
        assert resp.headers.get("X-Request-Id") == "my-rid"

    def test_production_filter_by_region(self, db):
        resp = _simulate_production_endpoint(db, {"region_code": "11"})
        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        for rec in body["data"]:
            assert rec["code_insee"] == "11"

    def test_export_200_with_data(self, db):
        resp = _simulate_export_endpoint(db, {})
        assert resp.status_code == 200
        assert resp.mimetype.startswith("text/csv")

    def test_export_content_disposition_header(self, db):
        resp = _simulate_export_endpoint(db, {})
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert ".csv" in resp.headers.get("Content-Disposition", "")

    def test_export_utf8_bom(self, db):
        resp = _simulate_export_endpoint(db, {})
        assert resp.status_code == 200
        body = resp.get_body()
        assert body[:3] == UTF8_BOM

    def test_export_404_no_data(self, db):
        resp = _simulate_export_endpoint(db, {"region_code": "ZZ"})
        assert resp.status_code == 404

    def test_export_request_id_header(self, db):
        resp = _simulate_export_endpoint(db, {}, request_id="exp-rid")
        assert resp.headers.get("X-Request-Id") == "exp-rid"


# ─── Task 5.4: Performance — <500ms on sample dataset ────────────────────────

class TestPerformance:
    """AC #2: NFR-P2 — response time < 500ms."""

    def test_production_query_under_500ms(self, db):
        """Baseline: <500ms on SQLite in-memory with small dataset."""
        start = time.perf_counter()
        query_production(db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Query took {elapsed_ms:.1f}ms — exceeds 500ms NFR-P2"

    def test_export_csv_under_500ms(self, db):
        start = time.perf_counter()
        export_to_csv(db)  # returns (bytes, filename, row_count)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"CSV export took {elapsed_ms:.1f}ms — exceeds 500ms NFR-P2"

    def test_production_filtered_query_under_500ms(self, db):
        start = time.perf_counter()
        query_production(db, region_code="11", limit=50)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"Filtered query took {elapsed_ms:.1f}ms"
