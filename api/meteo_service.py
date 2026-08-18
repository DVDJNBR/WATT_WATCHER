"""
Meteo Service — hourly temperature/wind/cloudcover per region from fact_meteo.
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)


def query_meteo(
    conn: Any,
    region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_meteo = "FACT_METEO" if sqlite_ else "fact_meteo"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"
    tbl_reg = "DIM_REGION" if sqlite_ else "dim_region"

    conditions = []
    params: list = []
    if region_code:
        conditions.append(f"r.code_insee = {ph}")
        params.append(region_code)
    if start_date:
        conditions.append(f"t.horodatage >= {ph}")
        params.append(start_date)
    if end_date:
        conditions.append(f"t.horodatage <= {ph}")
        params.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT t.horodatage, r.code_insee, r.nom_region,
               m.temperature_c, m.wind_speed_10m, m.cloudcover_pct
        FROM {tbl_meteo} m
        JOIN {tbl_time} t   ON t.id_date   = m.id_date
        JOIN {tbl_reg}  r   ON r.id_region = m.id_region
        {where}
        ORDER BY t.horodatage DESC
        LIMIT {ph}
    """
    params.append(limit)

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    data = [
        {
            "timestamp": str(row[0]),
            "code_insee": row[1],
            "region": row[2],
            "temperature_c": float(row[3]) if row[3] is not None else None,
            "wind_speed_10m": float(row[4]) if row[4] is not None else None,
            "cloudcover_pct": float(row[5]) if row[5] is not None else None,
        }
        for row in rows
    ]
    return {"data": data, "total_records": len(data), "request_id": request_id}
