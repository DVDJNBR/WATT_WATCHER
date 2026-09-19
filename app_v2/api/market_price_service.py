"""
Market Price Service — day-ahead spot price (EUR/MWh) from fact_market_price.
National, single-zone (France) — no region dimension, matching how ENTSO-E
publishes day-ahead prices (one bidding zone for mainland France).
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)


def query_market_price(
    conn: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_price = "FACT_MARKET_PRICE" if sqlite_ else "fact_market_price"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"

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
        SELECT t.horodatage, p.price_eur_mwh
        FROM {tbl_price} p
        JOIN {tbl_time} t ON t.id_date = p.id_date
        {where}
        ORDER BY t.horodatage ASC
        LIMIT {ph}
    """
    params.append(limit)

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    data = [
        {"timestamp": str(row[0]), "price_eur_mwh": float(row[1]) if row[1] is not None else None}
        for row in rows
    ]
    return {"data": data, "total_records": len(data), "request_id": request_id}
