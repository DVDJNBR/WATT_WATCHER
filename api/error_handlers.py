"""
Standardized error response factory.
Every response includes a request_id for traceability.
"""

import uuid
from typing import Optional


_STATUS_LABELS = {
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}


def error_response(
    status_code: int,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
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


def not_found(message: str = "No data found for the given parameters", request_id: Optional[str] = None) -> dict:
    """404 — query returned no results."""
    return error_response(404, message, request_id)


def server_error(message: str = "An unexpected error occurred", request_id: Optional[str] = None) -> dict:
    """500 — unhandled exception."""
    return error_response(500, message, request_id)
