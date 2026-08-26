"""
API Models — Story 4.1, Task 1.3

Request/response dataclasses for the production API endpoints.
No external deps — stdlib only.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProductionRequest:
    """Query parameters for GET /v1/production/regional."""

    region_code: Optional[str] = None   # INSEE code, e.g. "11"
    start_date: Optional[str] = None    # ISO 8601, e.g. "2025-06-01T00:00:00"
    end_date: Optional[str] = None      # ISO 8601
    source_type: Optional[str] = None   # e.g. "eolien", "solaire"
    limit: int = 100
    offset: int = 0


@dataclass
class ExportRequest:
    """Query parameters for GET /v1/export/csv."""

    region_code: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source_type: Optional[str] = None


@dataclass
class ProductionResponse:
    """Envelope for /v1/production/regional JSON response."""

    request_id: str
    total_records: int
    limit: int
    offset: int
    data: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "total_records": self.total_records,
            "limit": self.limit,
            "offset": self.offset,
            "data": self.data,
        }


def parse_production_request(params: dict) -> tuple["ProductionRequest", Optional[str]]:
    """
    Parse and validate query parameters for /v1/production/regional.

    Returns (request, error_message). error_message is None if valid.
    """
    try:
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))
    except (ValueError, TypeError):
        return ProductionRequest(), "limit and offset must be integers"

    if limit < 1 or limit > 1000:
        return ProductionRequest(), "limit must be between 1 and 1000"
    if offset < 0:
        return ProductionRequest(), "offset must be >= 0"

    return ProductionRequest(
        region_code=params.get("region_code"),
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        source_type=params.get("source_type"),
        limit=limit,
        offset=offset,
    ), None


def parse_export_request(params: dict) -> "ExportRequest":
    """Parse query parameters for /v1/export/csv."""
    return ExportRequest(
        region_code=params.get("region_code"),
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        source_type=params.get("source_type"),
    )
