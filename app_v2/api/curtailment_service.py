"""
Curtailment Risk Service — per-region share of national renewable surplus
during negative-price slots.

Deliberately excludes nuclear/hydro/thermal from the surplus calculation —
see frontend/src/components/FranceMap.jsx's existing comment on why a raw
regional prod/conso ratio is meaningless (nuclear-heavy regions structurally
export 300%+ of their own consumption at all times, negative price or not).
Only wind+solar are curtailable at short notice and are what RTE actually
throttles during oversupply, so the region driving a negative-price event is
the one with the largest wind+solar surplus over its own consumption at that
moment — not the one with the largest raw production.
"""

import logging
from typing import Any, Optional

from api.db import is_sqlite, placeholder

logger = logging.getLogger(__name__)

RENEWABLE_SOURCES = ("eolien", "solaire")


def query_curtailment_risk(
    conn: Any,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_flow = "FACT_ENERGY_FLOW" if sqlite_ else "fact_energy_flow"
    tbl_price = "FACT_MARKET_PRICE" if sqlite_ else "fact_market_price"
    tbl_reg = "DIM_REGION" if sqlite_ else "dim_region"
    tbl_src = "DIM_SOURCE" if sqlite_ else "dim_source"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"
    ren_in = ", ".join(f"{ph}" for _ in RENEWABLE_SOURCES)

    time_conditions = []
    params: list = []
    if start_date:
        time_conditions.append(f"t.horodatage >= {ph}")
        params.append(start_date)
    if end_date:
        if len(end_date) == 10:
            end_date = end_date + " 23:59:59"
        time_conditions.append(f"t.horodatage <= {ph}")
        params.append(end_date)
    time_where = ("AND " + " AND ".join(time_conditions)) if time_conditions else ""

    query = f"""
        WITH region_ren AS (
            SELECT f.id_date, f.id_region,
                   SUM(CASE WHEN s.source_name IN ({ren_in}) THEN f.valeur_mw ELSE 0 END) AS ren_mw,
                   AVG(f.consommation_mw) AS cons_mw
            FROM {tbl_flow} f
            JOIN {tbl_src} s ON f.id_source = s.id_source
            GROUP BY f.id_date, f.id_region
        ),
        neg_price_dates AS (
            SELECT p.id_date FROM {tbl_price} p WHERE p.price_eur_mwh < 0
        ),
        region_surplus AS (
            SELECT rr.id_region, rr.id_date,
                   CASE WHEN rr.ren_mw - rr.cons_mw > 0 THEN rr.ren_mw - rr.cons_mw ELSE 0 END AS surplus_mw
            FROM region_ren rr
            JOIN neg_price_dates npd ON rr.id_date = npd.id_date
            JOIN {tbl_time} t ON rr.id_date = t.id_date
            WHERE 1=1 {time_where}
        )
        SELECT r.code_insee, r.nom_region,
               SUM(rs.surplus_mw) AS total_surplus_mw,
               COUNT(DISTINCT rs.id_date) AS n_slots
        FROM region_surplus rs
        JOIN {tbl_reg} r ON rs.id_region = r.id_region
        GROUP BY r.code_insee, r.nom_region
        ORDER BY total_surplus_mw DESC
    """

    cursor = conn.cursor()
    cursor.execute(query, list(RENEWABLE_SOURCES) + params)
    rows = cursor.fetchall()

    grand_total = sum(float(row[2] or 0) for row in rows)
    data = [
        {
            "code_insee": row[0],
            "region": row[1],
            "surplus_mwh_15min": float(row[2] or 0),
            "share_pct": round(100 * float(row[2] or 0) / grand_total, 1) if grand_total > 0 else 0.0,
            "n_slots": row[3],
        }
        for row in rows
    ]

    return {
        "data": data,
        "national_surplus_mwh_15min": grand_total,
        "total_records": len(data),
        "request_id": request_id,
    }


def query_curtailment_calendar(
    conn: Any,
    request_id: Optional[str] = None,
) -> dict:
    """
    Day-by-day negative-price slot counts, for a calendar heatmap, plus the
    headline stats (total hours, record day) that make the pattern legible
    without reading the grid.
    """
    sqlite_ = is_sqlite(conn)
    ph_ = placeholder(conn)  # noqa: F841 - no params on this query, kept for consistency
    tbl_price = "FACT_MARKET_PRICE" if sqlite_ else "fact_market_price"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"

    date_expr = "date(t.horodatage)" if sqlite_ else "t.horodatage::date"
    query = f"""
        SELECT {date_expr} AS d, COUNT(*) AS n_slots, MIN(p.price_eur_mwh) AS min_price
        FROM {tbl_price} p
        JOIN {tbl_time} t ON p.id_date = t.id_date
        WHERE p.price_eur_mwh < 0
        GROUP BY {date_expr}
        ORDER BY {date_expr}
    """
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()

    days = [
        {
            "date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "n_slots": row[1],
            "min_price": float(row[2]),
        }
        for row in rows
    ]

    total_slots = sum(d["n_slots"] for d in days)
    record = min(days, key=lambda d: d["min_price"]) if days else None

    range_query = f"SELECT MIN(t.horodatage), MAX(t.horodatage) FROM {tbl_price} p JOIN {tbl_time} t ON p.id_date = t.id_date"
    cursor.execute(range_query)
    range_min, range_max = cursor.fetchone()

    return {
        "days": days,
        "range": {
            "start": range_min.date().isoformat() if range_min else None,
            "end": range_max.date().isoformat() if range_max else None,
        },
        "stats": {
            "total_days": len(days),
            "total_hours": round(total_slots / 4, 1),
            "record_date": record["date"] if record else None,
            "record_price": record["min_price"] if record else None,
        },
        "request_id": request_id,
    }
