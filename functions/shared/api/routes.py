"""
Route Definitions — Story 4.1 (Task 1.2) / Story 4.2 (Task 2.3) / Story 4.3 (Task 2)

URL path constants for the production API.
AC #3: RESTful conventions, /v1/ prefix for versioning.
Story 4.2 AC #4: PUBLIC_ROUTES lists endpoints exempt from @require_auth.
Story 4.3: /docs (Swagger UI) and /openapi.json (spec) are public.
"""

API_VERSION = "v1"
PREFIX = f"/{API_VERSION}"

# Protected endpoints (require Azure AD JWT)
PRODUCTION_REGIONAL = f"{PREFIX}/production/regional"
EXPORT_CSV = f"{PREFIX}/export/csv"

# Azure Functions route suffixes (without leading slash, per Azure SDK convention)
ROUTE_PRODUCTION = f"{API_VERSION}/production/regional"
ROUTE_EXPORT = f"{API_VERSION}/export/csv"

# Alerts endpoint
ALERTS = f"{PREFIX}/alerts"
ROUTE_ALERTS = f"{API_VERSION}/alerts"

# Public endpoints — exempt from @require_auth
ROUTE_HEALTH = "health"
ROUTE_DOCS = "docs"
ROUTE_OPENAPI_JSON = "openapi.json"

PUBLIC_ROUTES = {ROUTE_HEALTH, ROUTE_DOCS, ROUTE_OPENAPI_JSON}
