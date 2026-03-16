"""
Production Service — Story 4.1, Task 2

Queries Gold SQL FACT_ENERGY_FLOW + DIM joins.
Returns aggregated JSON: region/timestamp with pivoted source breakdown.

AC #1: Aggregated metrics from Gold SQL layer.
AC #2: Parameterized queries for <500ms (NFR-P2), index hint in docstring.
"""

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# SQL index recommendation (applied at DB provisioning, not here):
# CREATE INDEX IX_FACT_region_date ON FACT_ENERGY_FLOW (id_region, id_date);


def build_production_query(
    region_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    is_sqlite: bool = False,
) -> tuple[str, list]:
    """
    Build parameterized SQL query for production data.

    Returns (sql, params). Uses ? placeholders (pyodbc / sqlite3 compatible).
    AC #2: Parameterized → query plan caching, index usage.

    Note: LIMIT is applied on raw rows (one per source). Multiply by 10 to
    ensure enough rows are fetched before aggregation into (region, timestamp)
    records. Final pagination is applied in query_production() after aggregation.

    Args:
        is_sqlite: Use LIMIT syntax (SQLite) vs TOP syntax (SQL Server).
    """
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

    # Multiply SQL LIMIT by 10 (max ~8 sources per aggregated record) so that
    # enough raw rows are fetched to build `limit` aggregated records after pivot.
    sql_limit = (offset + limit) * 10

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
            ORDER BY t.horodatage ASC, r.code_insee
            LIMIT ?
        """
        params.append(sql_limit)
    else:
        # SQL Server: TOP clause at top of SELECT (? placeholder before WHERE params)
        sql = f"""
            SELECT TOP(?)
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
            ORDER BY t.horodatage ASC, r.code_insee
        """
        params.insert(0, sql_limit)

    return sql, params


def _to_json_safe(value):
    """Convert pyodbc non-JSON-serializable types (datetime, Decimal) to native Python."""
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
    Converts pyodbc-specific types (datetime, Decimal) to JSON-serializable types.
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
        conn: Any DB connection with cursor() support (pyodbc, sqlite3…).
        request_id: Trace ID; auto-generated if None.

    Returns:
        dict with request_id, total_records, limit, offset, data list.
    """
    request_id = request_id or str(uuid.uuid4())

    import sqlite3
    is_sqlite = isinstance(conn, sqlite3.Connection)

    sql, params = build_production_query(
        region_code, start_date, end_date, source_type, limit, offset,
        is_sqlite=is_sqlite,
    )

    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    data = _aggregate_rows(rows, cols)

    # Filter out records where all sources are 0 (RTE nulls filled by quality rules =
    # "data not yet available" slots — not actual zero-production measurements)
    data = [r for r in data if any(v != 0 for v in r["sources"].values())]

    # Apply pagination on aggregated records (not on raw rows)
    total = len(data)
    data = data[offset: offset + limit]

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
