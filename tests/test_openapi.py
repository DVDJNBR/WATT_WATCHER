"""
Tests for Story 4.3 — Automated Swagger/OpenAPI Documentation

Tasks: 4.1 (spec validation), 4.2 (Swagger UI endpoint), 4.3 (endpoint coverage).
"""

import json

import pytest

from functions.shared.api.openapi_spec import (
    build_spec,
    build_swagger_ui_html,
    OPENAPI_VERSION,
    API_TITLE,
    API_VERSION,
)
from functions.shared.api.routes import (
    ROUTE_HEALTH,
    ROUTE_DOCS,
    ROUTE_OPENAPI_JSON,
    PUBLIC_ROUTES,
    ROUTE_PRODUCTION,
    ROUTE_EXPORT,
)


# ─── Fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spec() -> dict:
    return build_spec()


# ─── Task 4.1: OpenAPI 3.0 structural validation ─────────────────────────────

class TestSpecStructure:
    """AC #1/#2: Spec is valid OpenAPI 3.0.3 structure."""

    def test_openapi_version(self, spec):
        assert spec["openapi"] == OPENAPI_VERSION
        assert spec["openapi"].startswith("3.")

    def test_info_block(self, spec):
        assert "info" in spec
        assert spec["info"]["title"] == API_TITLE
        assert "version" in spec["info"]
        assert "description" in spec["info"]

    def test_paths_block_present(self, spec):
        assert "paths" in spec
        assert isinstance(spec["paths"], dict)
        assert len(spec["paths"]) > 0

    def test_components_block(self, spec):
        assert "components" in spec
        assert "securitySchemes" in spec["components"]
        assert "schemas" in spec["components"]

    def test_servers_block(self, spec):
        assert "servers" in spec
        assert len(spec["servers"]) >= 1
        assert "url" in spec["servers"][0]

    def test_tags_defined(self, spec):
        assert "tags" in spec
        tag_names = [t["name"] for t in spec["tags"]]
        assert "Production" in tag_names
        assert "Export" in tag_names
        assert "System" in tag_names

    def test_spec_is_json_serializable(self, spec):
        """Spec must be fully JSON-serializable (no Python-only types)."""
        serialized = json.dumps(spec)
        reparsed = json.loads(serialized)
        assert reparsed["openapi"] == OPENAPI_VERSION

    def test_each_path_has_http_methods(self, spec):
        valid_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
        for path, item in spec["paths"].items():
            assert any(m in item for m in valid_methods), \
                f"Path {path!r} has no HTTP method"

    def test_each_operation_has_required_fields(self, spec):
        for path, item in spec["paths"].items():
            for method, op in item.items():
                assert "summary" in op, f"{method.upper()} {path} missing 'summary'"
                assert "operationId" in op, f"{method.upper()} {path} missing 'operationId'"
                assert "responses" in op, f"{method.upper()} {path} missing 'responses'"


# ─── Task 4.3: All endpoints present in spec ─────────────────────────────────

class TestEndpointCoverage:
    """AC #1: /health, /v1/production/regional, /v1/export/csv all documented."""

    def test_health_endpoint_in_spec(self, spec):
        assert "/health" in spec["paths"]

    def test_production_endpoint_in_spec(self, spec):
        assert "/v1/production/regional" in spec["paths"]

    def test_export_endpoint_in_spec(self, spec):
        assert "/v1/export/csv" in spec["paths"]

    def test_all_paths_have_get(self, spec):
        for path in ["/health", "/v1/production/regional", "/v1/export/csv"]:
            assert "get" in spec["paths"][path], f"GET missing for {path}"

    def test_production_has_all_query_params(self, spec):
        """AC #2: All documented params match the implementation."""
        params = spec["paths"]["/v1/production/regional"]["get"]["parameters"]
        param_names = {p["name"] for p in params}
        expected = {"region_code", "start_date", "end_date", "source_type", "limit", "offset"}
        assert expected == param_names

    def test_export_has_query_params_no_pagination(self, spec):
        """AC #2: Export params — no limit/offset (full export)."""
        params = spec["paths"]["/v1/export/csv"]["get"]["parameters"]
        param_names = {p["name"] for p in params}
        assert "region_code" in param_names
        assert "limit" not in param_names
        assert "offset" not in param_names

    def test_params_have_schema_and_description(self, spec):
        """AC #2: Each param has a type and description."""
        for path in ["/v1/production/regional", "/v1/export/csv"]:
            params = spec["paths"][path]["get"]["parameters"]
            for p in params:
                assert "schema" in p, f"Param {p['name']} in {path} missing 'schema'"
                assert "description" in p, f"Param {p['name']} in {path} missing 'description'"
                assert "type" in p["schema"] or "$ref" in p["schema"], \
                    f"Param {p['name']} schema has no type"

    def test_production_response_200_has_schema(self, spec):
        """AC #2: 200 response references ProductionResponse schema."""
        resp_200 = spec["paths"]["/v1/production/regional"]["get"]["responses"]["200"]
        content = resp_200["content"]["application/json"]["schema"]
        assert "$ref" in content
        assert "ProductionResponse" in content["$ref"]

    def test_export_response_200_is_csv(self, spec):
        """AC #2: Export 200 response is text/csv."""
        resp_200 = spec["paths"]["/v1/export/csv"]["get"]["responses"]["200"]
        assert "text/csv" in resp_200["content"]

    def test_error_responses_defined(self, spec):
        """AC #2: 400, 401, 404, 500 documented on production endpoint."""
        responses = spec["paths"]["/v1/production/regional"]["get"]["responses"]
        for code in ["400", "401", "404", "500"]:
            assert code in responses, f"HTTP {code} not documented"

    def test_error_response_schema_defined(self, spec):
        schemas = spec["components"]["schemas"]
        assert "ErrorResponse" in schemas
        props = schemas["ErrorResponse"]["properties"]
        assert "request_id" in props
        assert "status_code" in props
        assert "message" in props

    def test_production_record_schema_has_sources(self, spec):
        schemas = spec["components"]["schemas"]
        assert "ProductionRecord" in schemas
        props = schemas["ProductionRecord"]["properties"]
        assert "sources" in props
        assert "code_insee" in props
        assert "timestamp" in props


# ─── Task 4.3: Security documentation ────────────────────────────────────────

class TestSecurityDocumentation:
    """AC #3: ApiKeyAuth scheme documented; protected endpoints marked."""

    def test_apikey_auth_scheme_defined(self, spec):
        schemes = spec["components"]["securitySchemes"]
        assert "ApiKeyAuth" in schemes
        scheme = schemes["ApiKeyAuth"]
        assert scheme["type"] == "apiKey"
        assert scheme["in"] == "header"
        assert scheme["name"] == "X-Api-Key"

    def test_apikey_auth_has_description(self, spec):
        scheme = spec["components"]["securitySchemes"]["ApiKeyAuth"]
        assert "description" in scheme
        assert len(scheme["description"]) > 0

    def test_production_endpoint_requires_auth(self, spec):
        """AC #3: Protected endpoint has security requirement."""
        security = spec["paths"]["/v1/production/regional"]["get"].get("security", [])
        assert len(security) > 0
        assert any("ApiKeyAuth" in s for s in security)

    def test_export_endpoint_requires_auth(self, spec):
        security = spec["paths"]["/v1/export/csv"]["get"].get("security", [])
        assert len(security) > 0
        assert any("ApiKeyAuth" in s for s in security)

    def test_health_endpoint_is_public(self, spec):
        """AC #3: /health has security: [] (explicitly public)."""
        security = spec["paths"]["/health"]["get"].get("security")
        assert security == [], \
            "/health should have security: [] to explicitly opt out of global auth"

    def test_api_description_mentions_auth(self, spec):
        """AC #3: Auth method documented in API description."""
        description = spec["info"]["description"]
        assert "X-Api-Key" in description or "API key" in description.lower()


# ─── Task 4.2: Swagger UI HTML ───────────────────────────────────────────────

class TestSwaggerUI:
    """AC #1: Swagger UI HTML is valid and points to spec URL."""

    def test_swagger_ui_returns_html(self):
        html = build_swagger_ui_html()
        assert "<!DOCTYPE html>" in html
        assert "<html" in html

    def test_swagger_ui_loads_cdn(self):
        html = build_swagger_ui_html()
        assert "unpkg.com/swagger-ui-dist" in html

    def test_swagger_ui_points_to_spec_url(self):
        html = build_swagger_ui_html(openapi_json_url="/api/openapi.json")
        assert "/api/openapi.json" in html

    def test_swagger_ui_custom_spec_url(self):
        html = build_swagger_ui_html(openapi_json_url="/custom/spec.json")
        assert "/custom/spec.json" in html

    def test_swagger_ui_has_title(self):
        html = build_swagger_ui_html()
        assert API_TITLE in html

    def test_swagger_ui_has_swagger_bundle_js(self):
        html = build_swagger_ui_html()
        assert "swagger-ui-bundle.js" in html

    def test_swagger_ui_has_swagger_css(self):
        html = build_swagger_ui_html()
        assert "swagger-ui.css" in html

    def test_swagger_ui_has_dom_target(self):
        """Swagger UI needs a mount point."""
        html = build_swagger_ui_html()
        assert "swagger-ui" in html


# ─── Routes: public/protected classification ─────────────────────────────────

class TestRouteClassification:
    def test_docs_route_is_public(self):
        assert ROUTE_DOCS in PUBLIC_ROUTES

    def test_openapi_json_route_is_public(self):
        assert ROUTE_OPENAPI_JSON in PUBLIC_ROUTES

    def test_health_route_is_public(self):
        assert ROUTE_HEALTH in PUBLIC_ROUTES

    def test_production_route_not_public(self):
        assert ROUTE_PRODUCTION not in PUBLIC_ROUTES

    def test_export_route_not_public(self):
        assert ROUTE_EXPORT not in PUBLIC_ROUTES
