"""
Maintenance Service — grid maintenance events from fact_maintenance.
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)


def query_maintenance(
    conn: Any,
    region_code: Optional[str] = None,
    limit: int = 100,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_mnt = "FACT_MAINTENANCE" if sqlite_ else "fact_maintenance"
    tbl_reg = "DIM_REGION" if sqlite_ else "dim_region"

    if region_code:
        query = f"""
            SELECT m.event_id, r.code_insee, r.nom_region,
                   m.unit_name, m.event_type,
                   m.start_date, m.end_date, m.unavailable_mw
            FROM {tbl_mnt} m
            LEFT JOIN {tbl_reg} r ON r.id_region = m.id_region
            WHERE r.code_insee = {ph}
            ORDER BY m.start_date DESC
            LIMIT {ph}
        """
        params = [region_code, limit]
    else:
        query = f"""
            SELECT m.event_id, r.code_insee, r.nom_region,
                   m.unit_name, m.event_type,
                   m.start_date, m.end_date, m.unavailable_mw
            FROM {tbl_mnt} m
            LEFT JOIN {tbl_reg} r ON r.id_region = m.id_region
            ORDER BY m.start_date DESC
            LIMIT {ph}
        """
        params = [limit]

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    data = [
        {
            "event_id": row[0],
            "code_insee": row[1],
            "region": row[2],
            "unit_name": row[3],
            "event_type": row[4],
            "start_date": str(row[5]) if row[5] else None,
            "end_date": str(row[6]) if row[6] else None,
            "unavailable_mw": float(row[7]) if row[7] is not None else None,
        }
        for row in rows
    ]
    return {"data": data, "total_records": len(data), "request_id": request_id}
