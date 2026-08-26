"""
Capacity Service — installed capacity per region+source from fact_capacity.
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)


def query_capacity(
    conn: Any,
    region_code: Optional[str] = None,
    annee: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_cap = "FACT_CAPACITY" if sqlite_ else "fact_capacity"
    tbl_reg = "DIM_REGION" if sqlite_ else "dim_region"
    tbl_src = "DIM_SOURCE" if sqlite_ else "dim_source"

    conditions = []
    params: list = []
    if region_code:
        conditions.append(f"r.code_insee = {ph}")
        params.append(region_code)
    if annee:
        conditions.append(f"c.annee = {ph}")
        params.append(int(annee))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT r.code_insee, r.nom_region, s.source_name,
               c.puissance_installee_mw, c.annee
        FROM {tbl_cap} c
        JOIN {tbl_reg} r ON r.id_region = c.id_region
        JOIN {tbl_src} s ON s.id_source = c.id_source
        {where}
        ORDER BY r.code_insee, c.annee DESC, s.source_name
    """

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    data = [
        {
            "code_insee": row[0],
            "region": row[1],
            "source": row[2],
            "puissance_installee_mw": float(row[3]) if row[3] is not None else None,
            "annee": row[4],
        }
        for row in rows
    ]
    return {"data": data, "total_records": len(data), "request_id": request_id}
