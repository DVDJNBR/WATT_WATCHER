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
    # Ordered DESC so that a range wider than `limit` drops the OLDEST slots,
    # not the newest — a LIMIT on an ASC scan silently truncates the chart at
    # whatever point the history passed the cap. Reversed below so callers
    # still receive ascending chronological order.
    query = f"""
        SELECT t.horodatage, p.price_eur_mwh
        FROM {tbl_price} p
        JOIN {tbl_time} t ON t.id_date = p.id_date
        {where}
        ORDER BY t.horodatage DESC
        LIMIT {ph}
    """
    params.append(limit)

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = list(reversed(cursor.fetchall()))
    data = [
        {"timestamp": str(row[0]), "price_eur_mwh": float(row[1]) if row[1] is not None else None}
        for row in rows
    ]
    return {"data": data, "total_records": len(data), "request_id": request_id}


def query_day_ahead(
    conn: Any,
    request_id: Optional[str] = None,
) -> dict:
    """
    The most recent priced day, slot by slot: spot price alongside national
    consumption and wind+solar output.

    Residual load (consumption - wind - solar) is what the market actually
    prices, so returning the series together lets the chart show the cause
    next to the effect without a second round trip or a client-side join
    across 15 000 rows.

    Only wind and solar are subtracted: they are the two sources that produce
    whatever the weather allows rather than whatever the market asks for, so
    they come off demand instead of being dispatched against it.
    """
    sqlite_ = is_sqlite(conn)
    ph = placeholder(conn)
    tbl_price = "FACT_MARKET_PRICE" if sqlite_ else "fact_market_price"
    tbl_flow = "FACT_ENERGY_FLOW" if sqlite_ else "fact_energy_flow"
    tbl_src = "DIM_SOURCE" if sqlite_ else "dim_source"
    tbl_time = "DIM_TIME" if sqlite_ else "dim_time"
    day_expr = "date(t.horodatage)" if sqlite_ else "t.horodatage::date"

    # The most recent priced day that also has production: prices now run one
    # day ahead of the meter (ENTSO-E publishes tomorrow's day-ahead around
    # 12:45 CET), and picking the newest priced day outright landed on a day
    # with no consumption or wind/solar at all — the residual-load layer, half
    # the point of this chart, drew a flat line on zero. Tomorrow's prices are
    # still served by /v1/prices/regional and show up in the history layer.
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {day_expr} FROM {tbl_price} p JOIN {tbl_time} t ON t.id_date = p.id_date "
        f"WHERE EXISTS (SELECT 1 FROM {tbl_flow} f WHERE f.id_date = p.id_date) "
        f"ORDER BY t.horodatage DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return {"day": None, "data": [], "total_records": 0, "request_id": request_id}
    day = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])

    # consommation_mw repeats on every source row of a (slot, région), so it is
    # averaged per région before the régions are summed — summing it raw would
    # multiply national demand by the number of sources.
    query = f"""
        WITH per_region AS (
            SELECT f.id_date, f.id_region,
                   AVG(f.consommation_mw) AS cons_mw,
                   SUM(CASE WHEN s.source_name = 'eolien'  THEN f.valeur_mw ELSE 0 END) AS eolien_mw,
                   SUM(CASE WHEN s.source_name = 'solaire' THEN f.valeur_mw ELSE 0 END) AS solaire_mw
            FROM {tbl_flow} f
            JOIN {tbl_src} s ON s.id_source = f.id_source
            GROUP BY f.id_date, f.id_region
        ),
        national AS (
            SELECT id_date, SUM(cons_mw) AS cons_mw,
                   SUM(eolien_mw) AS eolien_mw, SUM(solaire_mw) AS solaire_mw,
                   COUNT(*) AS region_count
            FROM per_region GROUP BY id_date
        ),
        -- The newest slot is usually partial: régions report a few minutes
        -- apart, so summing it gives a national total missing two or three
        -- régions. Plotted, that reads as demand falling off a cliff at the
        -- end of the day. Only slots with the full complement of régions are
        -- returned as national figures.
        full_slots AS (SELECT MAX(region_count) AS n FROM national)
        SELECT t.horodatage, p.price_eur_mwh, n.cons_mw, n.eolien_mw, n.solaire_mw
        FROM {tbl_price} p
        JOIN {tbl_time} t ON t.id_date = p.id_date
        LEFT JOIN national n ON n.id_date = p.id_date
                             AND n.region_count = (SELECT n FROM full_slots)
        WHERE {day_expr} = {ph}
        ORDER BY t.horodatage ASC
    """
    cursor.execute(query, [day])

    data = []
    for horodatage, price, cons, eolien, solaire in cursor.fetchall():
        cons_f = float(cons) if cons is not None else None
        eol_f = float(eolien) if eolien is not None else None
        sol_f = float(solaire) if solaire is not None else None
        # Wind and solar are kept apart rather than summed: the chart stacks
        # them in the production tab's own colours, and a single "renewable"
        # total would blend the two into one meaningless band.
        ren_f = None if (eol_f is None or sol_f is None) else eol_f + sol_f
        data.append({
            "timestamp": str(horodatage),
            "price_eur_mwh": float(price) if price is not None else None,
            "consommation_mw": cons_f,
            "eolien_mw": eol_f,
            "solaire_mw": sol_f,
            "renouvelable_mw": ren_f,
            "residu_mw": (cons_f - ren_f) if (cons_f is not None and ren_f is not None) else None,
        })

    return {"day": day, "data": data, "total_records": len(data), "request_id": request_id}
