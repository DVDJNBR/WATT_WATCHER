"""
OpenAPI Spec Generator — Story 4.3, Task 1

Programmatically generates an OpenAPI 3.0.3 specification for the
GRID_POWER_STREAM API.

AC #1: All endpoints documented (production/regional, export/csv, health).
AC #2: Request params, response schemas, examples.
AC #3: ApiKeyAuth security scheme; protected endpoints marked.
"""

from __future__ import annotations

API_TITLE = "GRID_POWER_STREAM API"
API_VERSION = "1.0.0"
OPENAPI_VERSION = "3.0.3"

_APIKEY_AUTH_DESCRIPTION = (
    "API key passed in the X-Api-Key request header. "
    "Contact the administrator to obtain your key."
)

_API_DESCRIPTION = (
    "REST API for French regional electricity production and carbon intensity data.\n\n"
    "## Authentication\n\n"
    "All `/v1/*` endpoints require a valid **API key** in the `X-Api-Key` header.\n\n"
    "```\nX-Api-Key: <your-api-key>\n```\n\n"
    "Public endpoints (`/health`) do not require authentication."
)


# ─── Reusable schemas ────────────────────────────────────────────────────────

def _error_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "request_id":  {"type": "string", "format": "uuid", "example": "a1b2c3d4-..."},
            "status_code": {"type": "integer", "example": 400},
            "error":       {"type": "string", "example": "Bad Request"},
            "message":     {"type": "string", "example": "limit must be between 1 and 1000"},
            "details":     {"type": "object"},
        },
        "required": ["request_id", "status_code", "error", "message"],
    }


def _source_breakdown_schema() -> dict:
    source_names = ["nucleaire", "eolien", "solaire", "hydraulique",
                    "gaz", "charbon", "fioul", "bioenergies"]
    return {
        "type": "object",
        "description": "Production by energy source (MW)",
        "properties": {
            s: {"type": "number", "format": "float", "example": 450.0}
            for s in source_names
        },
    }


def _production_record_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "code_insee":     {"type": "string", "example": "11",
                               "description": "INSEE region code"},
            "region":         {"type": "string", "example": "Île-de-France"},
            "timestamp":      {"type": "string", "format": "date-time",
                               "example": "2025-06-15T10:00:00+00:00"},
            "sources":        _source_breakdown_schema(),
            "facteur_charge": {"type": "number", "format": "float",
                               "nullable": True, "example": 0.09},
        },
        "required": ["code_insee", "region", "timestamp", "sources"],
    }


def _production_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "request_id":    {"type": "string", "format": "uuid"},
            "total_records": {"type": "integer", "example": 12},
            "limit":         {"type": "integer", "example": 100},
            "offset":        {"type": "integer", "example": 0},
            "data":          {
                "type": "array",
                "items": {"$ref": "#/components/schemas/ProductionRecord"},
            },
        },
        "required": ["request_id", "total_records", "limit", "offset", "data"],
    }


# ─── Query parameter definitions ────────────────────────────────────────────

def _production_query_params() -> list[dict]:
    return [
        {
            "name": "region_code",
            "in": "query",
            "required": False,
            "description": "INSEE region code filter (e.g. '11' for Île-de-France)",
            "schema": {"type": "string", "example": "11"},
        },
        {
            "name": "start_date",
            "in": "query",
            "required": False,
            "description": "Start of time range (ISO 8601)",
            "schema": {"type": "string", "format": "date-time",
                       "example": "2025-06-01T00:00:00"},
        },
        {
            "name": "end_date",
            "in": "query",
            "required": False,
            "description": "End of time range (ISO 8601)",
            "schema": {"type": "string", "format": "date-time",
                       "example": "2025-06-30T23:59:59"},
        },
        {
            "name": "source_type",
            "in": "query",
            "required": False,
            "description": "Filter by energy source",
            "schema": {
                "type": "string",
                "enum": ["nucleaire", "eolien", "solaire", "hydraulique",
                         "gaz", "charbon", "fioul", "bioenergies"],
            },
        },
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "description": "Max records to return (1–1000, default 100)",
            "schema": {"type": "integer", "minimum": 1, "maximum": 1000,
                       "default": 100},
        },
        {
            "name": "offset",
            "in": "query",
            "required": False,
            "description": "Pagination offset (default 0)",
            "schema": {"type": "integer", "minimum": 0, "default": 0},
        },
    ]


def _export_query_params() -> list[dict]:
    """Subset of production params — no pagination for CSV export."""
    return [p for p in _production_query_params()
            if p["name"] not in ("limit", "offset")]


# ─── Path definitions ────────────────────────────────────────────────────────

def _health_path() -> dict:
    return {
        "get": {
            "summary": "Health check",
            "description": "Returns API health status. No authentication required.",
            "operationId": "getHealth",
            "tags": ["System"],
            "security": [],  # explicitly public
            "responses": {
                "200": {
                    "description": "API is healthy",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status":  {"type": "string", "example": "healthy"},
                                    "version": {"type": "string", "example": API_VERSION},
                                },
                            },
                            "example": {"status": "healthy", "version": API_VERSION},
                        }
                    },
                }
            },
        }
    }


def _production_path() -> dict:
    return {
        "get": {
            "summary": "Regional electricity production",
            "description": (
                "Returns aggregated energy production data from the Gold SQL layer, "
                "grouped by region and timestamp with per-source breakdown."
            ),
            "operationId": "getProductionRegional",
            "tags": ["Production"],
            "security": [{"ApiKeyAuth": []}],
            "parameters": _production_query_params(),
            "responses": {
                "200": {
                    "description": "Aggregated production data",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ProductionResponse"},
                        }
                    },
                },
                "400": {
                    "description": "Invalid query parameters",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
                "401": {
                    "description": "Missing or invalid X-Api-Key header",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
                "404": {
                    "description": "No data found for the given parameters",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
                "500": {
                    "description": "Internal server error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
            },
        }
    }


def _export_path() -> dict:
    return {
        "get": {
            "summary": "Export production data as CSV",
            "description": (
                "Downloads production data as a CSV file. "
                "UTF-8 BOM + semicolon separator for FR locale Excel compatibility."
            ),
            "operationId": "getExportCsv",
            "tags": ["Export"],
            "security": [{"ApiKeyAuth": []}],
            "parameters": _export_query_params(),
            "responses": {
                "200": {
                    "description": "CSV file download",
                    "headers": {
                        "Content-Disposition": {
                            "schema": {"type": "string"},
                            "example": 'attachment; filename="production_energie_abc12345.csv"',
                        }
                    },
                    "content": {
                        "text/csv": {
                            "schema": {"type": "string", "format": "binary"},
                        }
                    },
                },
                "401": {
                    "description": "Missing or invalid X-Api-Key header",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
                "404": {
                    "description": "No data found",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
                "500": {
                    "description": "Internal server error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
            },
        }
    }


# ─── Public builder ───────────────────────────────────────────────────────────

def build_spec() -> dict:
    """
    Generate the complete OpenAPI 3.0.3 specification dict.

    AC #1: All endpoints included.
    AC #2: Parameters, schemas, examples documented.
    AC #3: BearerAuth scheme defined; protected endpoints marked.
    """
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": API_TITLE,
            "description": _API_DESCRIPTION,
            "version": API_VERSION,
            "contact": {
                "name": "GRID_POWER_STREAM",
            },
        },
        "servers": [
            {"url": "/api", "description": "Azure Functions host"},
        ],
        "tags": [
            {"name": "System",     "description": "Health and system endpoints"},
            {"name": "Production", "description": "Regional electricity production data"},
            {"name": "Export",     "description": "Data export endpoints"},
        ],
        "paths": {
            "/health":                  _health_path(),
            "/v1/production/regional":  _production_path(),
            "/v1/export/csv":           _export_path(),
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Api-Key",
                    "description": _APIKEY_AUTH_DESCRIPTION,
                }
            },
            "schemas": {
                "ProductionRecord":   _production_record_schema(),
                "ProductionResponse": _production_response_schema(),
                "ErrorResponse":      _error_response_schema(),
            },
        },
    }


def build_swagger_ui_html(openapi_json_url: str = "/api/openapi.json") -> str:
    """
    Generate Swagger UI HTML page pointing to the OpenAPI spec URL.

    AC #1: Functional Swagger UI at /docs.
    Uses CDN (unpkg.com/swagger-ui-dist) — no bundled assets needed.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{API_TITLE} — API Docs</title>
  <link rel="stylesheet"
        href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{
      url: "{openapi_json_url}",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
      deepLinking: true,
      persistAuthorization: true
    }});
  </script>
</body>
</html>
"""
