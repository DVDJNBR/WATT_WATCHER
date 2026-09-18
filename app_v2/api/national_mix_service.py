"""
National Mix Service — gaz/charbon/fioul fossil-thermal split from
fact_national_mix. France-wide only, no region dimension (RTE only
publishes this breakdown nationally, not per-region — see
functions/shared/transformations/national_silver.py).
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)


def query_national_mix(
    conn: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_fact = "FACT_NATIONAL_MIX" if sqlite_ else "fact_national_mix"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"
    tbl_src = "DIM_SOURCE" if sqlite_ else "dim_source"

    conditions = []
    params: list = []
    if start_date:
        conditions.append(f"t.horodatage >= {ph}")
        params.append(start_date)
    if end_date:
        conditions.append(f"t.horodatage <= {ph}")
        params.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT t.horodatage, s.source_name, f.valeur_mw
        FROM {tbl_fact} f
        JOIN {tbl_time}   t ON t.id_date   = f.id_date
        JOIN {tbl_src}    s ON s.id_source = f.id_source
        {where}
        ORDER BY t.horodatage DESC
        LIMIT {ph}
    """
    # limit applies to raw (timestamp, source) rows — 3 sources per timestamp
    params.append(limit * 3)

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()

    by_ts: dict[str, dict] = {}
    for horodatage, source_name, valeur_mw in rows:
        ts = str(horodatage)
        if ts not in by_ts:
            by_ts[ts] = {"timestamp": ts, "sources": {}}
        by_ts[ts]["sources"][source_name] = float(valeur_mw) if valeur_mw is not None else None

    data = sorted(by_ts.values(), key=lambda r: r["timestamp"])[-limit:]
    return {"data": data, "total_records": len(data), "request_id": request_id}
