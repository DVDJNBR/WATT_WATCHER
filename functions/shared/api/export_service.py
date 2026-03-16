"""
Export Service — Story 4.1, Task 3

Generates CSV from Gold SQL production data.
AC #4: Downloadable CSV with proper Content-Type / Content-Disposition headers.
AC #4: UTF-8 BOM + semicolon separator for FR locale Excel compatibility.
"""

import csv
import io
import logging
import uuid
from typing import Any, Optional

from shared.api.production_service import build_production_query

logger = logging.getLogger(__name__)

# AC #4: FR locale Excel compatibility
CSV_DELIMITER = ";"
CSV_DECIMAL_SEP = ","
UTF8_BOM = b"\xef\xbb\xbf"

# Human-readable column headers (FR)
COLUMN_LABELS = {
    "code_insee": "Code INSEE",
    "nom_region": "Région",
    "horodatage": "Horodatage",
    "source_name": "Source",
    "valeur_mw": "Valeur (MW)",
    "facteur_charge": "Facteur de charge",
}


def _format_cell(value: Any) -> str:
    """Format a cell for FR locale CSV (comma decimal separator)."""
    if value is None:
        return ""
    if isinstance(value, float):
        return str(round(value, 4)).replace(".", CSV_DECIMAL_SEP)
    return str(value)


def export_to_csv(
    conn: Any,
    region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source_type: Optional[str] = None,
    request_id: Optional[str] = None,
) -> tuple[bytes, str, int]:
    """
    Generate CSV bytes from Gold SQL data.

    AC #4: Returns (csv_bytes, filename, row_count).
    Headers are set by the HTTP handler:
      Content-Type: text/csv; charset=utf-8
      Content-Disposition: attachment; filename=<filename>

    Args:
        conn: DB connection with cursor() support.
        request_id: Trace ID for filename suffix; auto-generated if None.

    Returns:
        (csv_bytes, filename, data_row_count) — bytes include UTF-8 BOM.
        data_row_count is 0 when query returns no results.
    """
    request_id = request_id or str(uuid.uuid4())

    import sqlite3
    is_sqlite = isinstance(conn, sqlite3.Connection)

    # Fetch all rows (no pagination for CSV — capped at 10 000 for safety)
    sql, params = build_production_query(
        region_code, start_date, end_date, source_type,
        limit=10_000, offset=0, is_sqlite=is_sqlite,
    )

    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    col_names = [d[0] for d in cursor.description]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=CSV_DELIMITER, lineterminator="\r\n")

    # Header with human-readable labels
    writer.writerow([COLUMN_LABELS.get(c, c) for c in col_names])

    for row in rows:
        writer.writerow([_format_cell(v) for v in row])

    csv_bytes = UTF8_BOM + output.getvalue().encode("utf-8")

    region_part = f"_{region_code}" if region_code else ""
    filename = f"production_energie{region_part}_{request_id[:8]}.csv"

    logger.debug(
        "CSV export: region=%s, %d rows → %s [req=%s]",
        region_code, len(rows), filename, request_id,
    )

    return csv_bytes, filename, len(rows)
