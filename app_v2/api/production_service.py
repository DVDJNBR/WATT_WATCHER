"""
Production Service — Story 4.1, Task 2

Queries Gold SQL FACT_ENERGY_FLOW + DIM joins.
Returns aggregated JSON: region/timestamp with pivoted source breakdown.

AC #1: Aggregated metrics from Gold SQL layer.
AC #2: Parameterized queries for <500ms (NFR-P2), index hint in docstring.
"""

import logging
import uuid
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# SQL index recommendation (applied at DB provisioning, not here):
# CREATE INDEX IX_FACT_region_date ON FACT_ENERGY_FLOW (id_region, id_date);


def _production_filters(
    region_code: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    source_type: Optional[str],
) -> tuple[str, list]:
    """WHERE clause (with ? placeholders) and its params, shared by every production query."""
    where_clauses: list[str] = []
    params: list[Any] = []

    if region_code:
        where_clauses.append("r.code_insee = ?")
        params.append(region_code)

    if start_date:
        where_clauses.append("t.horodatage >= ?")
        params.append(start_date)

    if end_date:
        where_clauses.append("t.horodatage <= ?")
        # Date-only string (YYYY-MM-DD) → include the whole day up to 23:59:59
        if len(end_date) == 10:
            end_date = end_date + " 23:59:59"
        params.append(end_date)

    if source_type:
        where_clauses.append("s.source_name = ?")
        params.append(source_type)

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return where, params


def build_production_query(
    region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    is_sqlite: bool = False,
    max_rows: Optional[int] = None,
) -> tuple[str, list]:
    """
    Build parameterized SQL query for production data.

    Returns (sql, params). Uses ? placeholders for SQLite, %s for PostgreSQL.
    AC #2: Parameterized → query plan caching, index usage.

    Note: LIMIT is applied on raw rows (one per source). Multiply by 10 to
    ensure enough rows are fetched before aggregation into (region, timestamp)
    records. Final pagination is applied in query_production() after aggregation.

    Args:
        is_sqlite: Use SQLite syntax (? placeholders, uppercase tables) vs
                   PostgreSQL syntax (%s placeholders, lowercase tables).
        max_rows: Hard cap on raw rows, overriding the span-based one below.
    """
    where, params = _production_filters(region_code, start_date, end_date, source_type)

    # ORDER BY ... DESC: fetch the most recent rows in the (optionally
    # date-bounded) range first. Matches the DESC-then-limit pattern used by
    # meteo_service/maintenance_service; the frontend re-sorts ascending for
    # display.
    #
    # sql_limit must cover every raw row in the requested date range, not
    # just enough for one page — pagination happens in Python, after this
    # fetch, on the pivoted (region, timestamp) records. A limit sized only
    # to `(offset + limit)` silently truncates any range wider than one page
    # to its most recent slice: a caller asking for 14 days of history would
    # only ever see the last day or two. Size the cap from the actual date
    # span when both bounds are given (12 regions x ~9 sources x 96 slots/day
    # for that many days), otherwise fall back to a generous fixed cap.
    MAX_SQL_LIMIT = 700_000  # ~60 days at full regional/source density
    sql_limit = MAX_SQL_LIMIT
    if start_date and end_date:
        try:
            span_days = (date.fromisoformat(end_date[:10]) - date.fromisoformat(start_date[:10])).days + 1
            sql_limit = min(MAX_SQL_LIMIT, max((offset + limit) * 10, span_days * 12 * 9 * 96))
        except ValueError:
            pass
    if max_rows is not None:
        sql_limit = min(sql_limit, max_rows)

    if is_sqlite:
        # SQLite: LIMIT clause at end
        sql = f"""
            SELECT
                r.code_insee,
                r.nom_region,
                t.horodatage,
                s.source_name,
                f.valeur_mw,
                f.facteur_charge,
                f.consommation_mw
            FROM FACT_ENERGY_FLOW f
            JOIN DIM_REGION r ON f.id_region = r.id_region
            JOIN DIM_TIME t ON f.id_date = t.id_date
            JOIN DIM_SOURCE s ON f.id_source = s.id_source
            {where}
            ORDER BY t.horodatage DESC, r.code_insee
            LIMIT ?
        """
        params.append(sql_limit)
    else:
        # PostgreSQL: LIMIT clause at end with %s placeholder
        where_pg = where.replace("?", "%s")
        sql = f"""
            SELECT
                r.code_insee,
                r.nom_region,
                t.horodatage,
                s.source_name,
                f.valeur_mw,
                f.facteur_charge,
                f.consommation_mw
            FROM fact_energy_flow f
            JOIN dim_region r ON f.id_region = r.id_region
            JOIN dim_time t ON f.id_date = t.id_date
            JOIN dim_source s ON f.id_source = s.id_source
            {where_pg}
            ORDER BY t.horodatage DESC, r.code_insee
            LIMIT %s
        """
        params.append(sql_limit)

    return sql, params


def _to_json_safe(value):
    """Convert non-JSON-serializable types (datetime, Decimal) to native Python."""
    if value is None:
        return None
    # datetime / date → ISO string
    if hasattr(value, "isoformat"):
        return value.isoformat()
    # Decimal → float
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value)
    except ImportError:
        pass
    return value


def _aggregate_rows(rows: list, cols: list[str]) -> list[dict]:
    """
    Pivot flat SQL rows into region/timestamp records with source breakdown.

    AC #3: {region, timestamp, sources: {eolien, ...}, facteur_charge, consommation_mw}
    Converts DB-specific types (datetime, Decimal) to JSON-serializable types.
    consommation_mw is a region/timestamp-level field (not per source) — taken from first row.
    """
    aggregated: dict[tuple, dict] = {}

    for row in rows:
        r = dict(zip(cols, row))
        ts = _to_json_safe(r["horodatage"])
        key = (r["code_insee"], ts)

        if key not in aggregated:
            aggregated[key] = {
                "code_insee": r["code_insee"],
                "region": r["nom_region"],
                "timestamp": ts,
                "sources": {},
                "facteur_charge": _to_json_safe(r["facteur_charge"]),
                "consommation_mw": _to_json_safe(r["consommation_mw"]),
            }

        source = r["source_name"]
        aggregated[key]["sources"][source] = _to_json_safe(r["valeur_mw"])

    return list(aggregated.values())


def query_production(
    conn: Any,
    region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    request_id: Optional[str] = None,
) -> dict:
    """
    Execute production query and return aggregated JSON response.

    AC #1: Returns aggregated metrics from Gold SQL FACT_ENERGY_FLOW + DIM joins.
    AC #2: Parameterized queries → <500ms with proper indexes.

    Args:
        conn: Any DB connection with cursor() support (psycopg2, sqlite3…).
        request_id: Trace ID; auto-generated if None.

    Returns:
        dict with request_id, total_records, limit, offset, data list.
    """
    request_id = request_id or str(uuid.uuid4())

    import sqlite3
    is_sqlite = isinstance(conn, sqlite3.Connection)

    # Paginate in SQL, on (région, horodatage) keys, then fetch only that
    # page's rows. Fetching the whole range and paginating the pivoted records
    # in Python held up to 700k raw rows at once: a 3-month range peaked at
    # ~620 MB and got the 512 MB API container OOM-killed.
    #
    # A key is kept only if one of its sources is non-zero — RTE nulls filled
    # by quality rules leave all-zero "data not yet available" slots, not
    # actual zero-production measurements. NULL counts as non-zero, as the
    # former Python filter (`v != 0`) did.
    where, params = _production_filters(region_code, start_date, end_date, source_type)
    ph = "?" if is_sqlite else "%s"
    fact, region, time_, source = (
        ("FACT_ENERGY_FLOW", "DIM_REGION", "DIM_TIME", "DIM_SOURCE") if is_sqlite
        else ("fact_energy_flow", "dim_region", "dim_time", "dim_source")
    )
    joins = f"""
        FROM {fact} f
        JOIN {region} r ON f.id_region = r.id_region
        JOIN {time_} t ON f.id_date = t.id_date
        JOIN {source} s ON f.id_source = s.id_source
    """
    where = where.replace("?", ph)
    keys_sql = f"""
        SELECT f.id_date, f.id_region, t.horodatage, r.code_insee
        {joins}
        {where}
        GROUP BY f.id_date, f.id_region, t.horodatage, r.code_insee
        HAVING SUM(CASE WHEN f.valeur_mw IS NULL OR f.valeur_mw <> 0 THEN 1 ELSE 0 END) > 0
    """

    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM ({keys_sql}) k", params)
    total = cursor.fetchone()[0]

    cursor.execute(
        f"""
        WITH page AS (
            {keys_sql}
            ORDER BY t.horodatage DESC, r.code_insee
            LIMIT {ph} OFFSET {ph}
        )
        SELECT r.code_insee, r.nom_region, t.horodatage, s.source_name,
               f.valeur_mw, f.facteur_charge, f.consommation_mw
        {joins}
        JOIN page p ON p.id_date = f.id_date AND p.id_region = f.id_region
        {where}
        ORDER BY t.horodatage DESC, r.code_insee
        """,
        params + [limit, offset] + params,
    )
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = _aggregate_rows(rows, cols)

    logger.debug(
        "production query: region=%s, start=%s, end=%s → %d/%d records [req=%s]",
        region_code, start_date, end_date, len(data), total, request_id,
    )

    return {
        "request_id": request_id,
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "data": data,
    }
