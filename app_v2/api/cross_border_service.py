"""
Cross-Border Flow Service — net physical export/import per border from
fact_cross_border_flow. Positive flow_mw = France exporting, negative =
France importing (see functions/shared/stages/cross_border_stage.py).
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)

BORDER_LABELS = {
    "GB": "Royaume-Uni",
    "CH": "Suisse",
    "IT": "Italie",
    "ES": "Espagne",
}


def query_cross_border(
    conn: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_flow = "FACT_CROSS_BORDER_FLOW" if sqlite_ else "fact_cross_border_flow"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"

    where = []
    params: list = []
    if start_date:
        where.append(f"t.horodatage >= {ph}")
        params.append(start_date)
    if end_date:
        where.append(f"t.horodatage <= {ph}")
        params.append(end_date)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    query = f"""
        SELECT t.horodatage, f.border_code, f.flow_mw
        FROM {tbl_flow} f
        JOIN {tbl_time} t ON t.id_date = f.id_date
        {where_clause}
        ORDER BY t.horodatage ASC
    """
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()

    data = [
        {
            "timestamp": str(row[0]),
            "border_code": row[1],
            "border_label": BORDER_LABELS.get(row[1], row[1]),
            "flow_mw": float(row[2]) if row[2] is not None else None,
        }
        for row in rows
    ]

    # Net total per border over the requested range — the number the
    # Sankey's 3rd stage actually needs, computed here rather than making
    # the frontend re-aggregate every point.
    totals: dict[str, float] = {}
    for row in data:
        totals[row["border_code"]] = totals.get(row["border_code"], 0.0) + (row["flow_mw"] or 0.0)
    summary = [
        {"border_code": code, "border_label": BORDER_LABELS.get(code, code), "net_mwh": round(v, 1)}
        for code, v in totals.items()
    ]

    return {"data": data, "summary": summary, "total_records": len(data), "request_id": request_id}
