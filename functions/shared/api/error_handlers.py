"""
Error Handlers — Story 4.1, Task 4.1

Standardized error response factory.
AC #3: Proper HTTP status codes (200, 400, 401, 404, 500).
AC #4: request_id included in all responses for traceability.
"""

import uuid
from typing import Optional


_STATUS_LABELS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    500: "Internal Server Error",
}


def error_response(
    status_code: int,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
    """
    Build a standardized error response dict.

    AC #4: request_id is always present.
    """
    return {
        "request_id": request_id or str(uuid.uuid4()),
        "status_code": status_code,
        "error": _STATUS_LABELS.get(status_code, "Error"),
        "message": message,
        "details": details or {},
    }


def bad_request(message: str, request_id: Optional[str] = None) -> dict:
    """400 — invalid query parameters."""
    return error_response(400, message, request_id)


def unauthorized(request_id: Optional[str] = None) -> dict:
    """401 — missing or invalid authentication."""
    return error_response(401, "Authentication required", request_id)


def not_found(message: str = "No data found for the given parameters", request_id: Optional[str] = None) -> dict:
    """404 — query returned no results."""
    return error_response(404, message, request_id)


def forbidden(message: str, request_id: Optional[str] = None) -> dict:
    """403 — authenticated but not authorized (e.g., unconfirmed account)."""
    return error_response(403, message, request_id)


def conflict(message: str, request_id: Optional[str] = None) -> dict:
    """409 — resource already exists."""
    return error_response(409, message, request_id)


def server_error(message: str = "An unexpected error occurred", request_id: Optional[str] = None) -> dict:
    """500 — unhandled exception."""
    return error_response(500, message, request_id)
