"""
inject_test_data.py — Admin script to inject fake Gold data for alert pipeline testing.

Injects a sentinel row into FACT_ENERGY_FLOW using a far-future timestamp
("2099-12-31T23:59:00") so that alert_detector.detect() always picks it up as the
latest data point, triggering the desired alert condition for the target region.

Usage:
    # Inject under_production for region FR (prod < conso):
        python inject_test_data.py --mode inject --region FR --alert-type under_production
        python inject_test_data.py --mode inject --region FR --alert-type under_production --prod-mw 4000 --conso-mw 6000

    # Inject over_production for region IDF:
        python inject_test_data.py --mode inject --region IDF --alert-type over_production --prod-mw 8000 --conso-mw 5000

    # Remove all injected data (restores real data as latest):
        python inject_test_data.py --mode restore

Environment variables:
    SUPABASE_CONNECTION_STRING            PostgreSQL connection string (production/staging)
    LOCAL_GOLD_DB           Path to local SQLite gold.db (local dev override)

If neither is set, defaults to gold.db in the project root.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SENTINEL_TS = "2099-12-31T23:59:00"
TEST_SOURCE = "TEST_INJECTION"

# Default values that guarantee the desired alert direction
_DEFAULTS = {
    "under_production": {"prod_mw": 4000.0, "conso_mw": 6000.0},
    "over_production":  {"prod_mw": 8000.0, "conso_mw": 5000.0},
}


def _get_connection() -> Any:
    """
    Return a Gold DB connection.

    Priority:
      1. SUPABASE_CONNECTION_STRING env var → psycopg2 (PostgreSQL/Supabase)
      2. LOCAL_GOLD_DB env var → sqlite3
      3. Default → sqlite3 on gold.db in project root
    """
    db_url = os.environ.get("SUPABASE_CONNECTION_STRING", "")
    if db_url:
        import psycopg2  # type: ignore[import]
        return psycopg2.connect(db_url)
    import sqlite3
    local_db = os.environ.get(
        "LOCAL_GOLD_DB",
        str(Path(__file__).parent.parent.parent / "gold.db"),
    )
    logger.info("Using local SQLite: %s", local_db)
    return sqlite3.connect(local_db)


def _last_inserted_id(cursor: Any, conn: Any) -> int:
    """Return the last auto-generated row ID — compatible with sqlite3 and psycopg2."""
    if "sqlite3" in type(conn).__module__:
        return cursor.lastrowid
    # psycopg2: use RETURNING id — caller must have used INSERT ... RETURNING id
    return int(cursor.fetchone()[0])


def _ensure_row(cursor: Any, conn: Any, select_sql: str, insert_sql: str,
                select_params: tuple, insert_params: tuple) -> int:
    """Return existing row ID or insert and return new ID."""
    is_pg = "sqlite3" not in type(conn).__module__
    if is_pg:
        select_sql = select_sql.replace("?", "%s")
        insert_sql = insert_sql.replace("?", "%s")
        # Append RETURNING id for PostgreSQL to retrieve the generated PK
        if "RETURNING" not in insert_sql.upper():
            insert_sql = insert_sql.rstrip(";") + " RETURNING id"
    cursor.execute(select_sql, select_params)
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(insert_sql, insert_params)
    return _last_inserted_id(cursor, conn)


def inject(conn: Any, region_code: str, alert_type: str,
           prod_mw: float, conso_mw: float) -> None:
    """
    Insert a sentinel FACT_ENERGY_FLOW row that triggers the given alert_type.

    Uses timestamp SENTINEL_TS so detect() always treats it as the latest data.
    Not idempotent for FACT_ENERGY_FLOW: calling inject twice for the same region
    inserts two rows (both detected, since they share the same MAX timestamp).
    Call restore() first to clean up before re-injecting.

    Args:
        conn:        DB connection (psycopg2 or sqlite3).
        region_code: Target region code_insee (e.g. "FR", "IDF").
        alert_type:  "under_production" (prod < conso) or "over_production" (prod > conso).
        prod_mw:     Production value in MW.
        conso_mw:    Consumption value in MW.
    """
    if alert_type not in ("under_production", "over_production"):
        raise ValueError(f"Invalid alert_type '{alert_type}'")
    if alert_type == "under_production" and prod_mw >= conso_mw:
        raise ValueError(f"under_production requires prod_mw < conso_mw (got {prod_mw} >= {conso_mw})")
    if alert_type == "over_production" and prod_mw <= conso_mw:
        raise ValueError(f"over_production requires prod_mw > conso_mw (got {prod_mw} <= {conso_mw})")

    cursor = conn.cursor()
    is_pg = "sqlite3" not in type(conn).__module__
    ph = "%s" if is_pg else "?"

    id_date = _ensure_row(
        cursor, conn,
        f"SELECT id_date FROM DIM_TIME WHERE horodatage = ?",
        f"INSERT INTO DIM_TIME (horodatage) VALUES (?)",
        (SENTINEL_TS,), (SENTINEL_TS,),
    )

    id_region = _ensure_row(
        cursor, conn,
        f"SELECT id_region FROM DIM_REGION WHERE code_insee = ?",
        f"INSERT INTO DIM_REGION (code_insee, nom_region) VALUES (?, ?)",
        (region_code,), (region_code, region_code),
    )

    id_source = _ensure_row(
        cursor, conn,
        f"SELECT id_source FROM DIM_SOURCE WHERE source_name = ?",
        f"INSERT INTO DIM_SOURCE (source_name) VALUES (?)",
        (TEST_SOURCE,), (TEST_SOURCE,),
    )

    fact_tbl = "fact_energy_flow" if is_pg else "FACT_ENERGY_FLOW"
    cursor.execute(
        f"INSERT INTO {fact_tbl} (id_region, id_date, id_source, valeur_mw, consommation_mw) "
        f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
        (id_region, id_date, id_source, prod_mw, conso_mw),
    )
    conn.commit()
    logger.info(
        "Injected: region=%s alert_type=%s prod=%.0f MW conso=%.0f MW (sentinel ts=%s)",
        region_code, alert_type, prod_mw, conso_mw, SENTINEL_TS,
    )


def restore(conn: Any) -> None:
    """
    Remove all injected test data.

    Deletes:
      - FACT_ENERGY_FLOW rows for source TEST_INJECTION at sentinel timestamp
      - DIM_TIME sentinel row

    DIM_SOURCE TEST_INJECTION and DIM_REGION entries are kept (harmless).
    Real production data is untouched.
    """
    cursor = conn.cursor()
    is_pg = "sqlite3" not in type(conn).__module__
    ph = "%s" if is_pg else "?"
    fact_tbl = "fact_energy_flow" if is_pg else "FACT_ENERGY_FLOW"
    src_tbl = "dim_source" if is_pg else "DIM_SOURCE"
    time_tbl = "dim_time" if is_pg else "DIM_TIME"

    cursor.execute(
        f"SELECT id_source FROM {src_tbl} WHERE source_name = {ph}", (TEST_SOURCE,)
    )
    src_row = cursor.fetchone()

    cursor.execute(
        f"SELECT id_date FROM {time_tbl} WHERE horodatage = {ph}", (SENTINEL_TS,)
    )
    time_row = cursor.fetchone()

    if src_row and time_row:
        id_source = src_row[0]
        id_date = time_row[0]
        cursor.execute(
            f"SELECT COUNT(*) FROM {fact_tbl} WHERE id_source = {ph} AND id_date = {ph}",
            (id_source, id_date),
        )
        deleted_facts = cursor.fetchone()[0]
        cursor.execute(
            f"DELETE FROM {fact_tbl} WHERE id_source = {ph} AND id_date = {ph}",
            (id_source, id_date),
        )
        cursor.execute(f"DELETE FROM {time_tbl} WHERE horodatage = {ph}", (SENTINEL_TS,))
        conn.commit()
        logger.info("Restored: removed %d FACT_ENERGY_FLOW row(s) and sentinel DIM_TIME row.", deleted_facts)
    else:
        logger.info("Restore: no injected data found — nothing to remove.")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inject or restore fake Gold data for alert pipeline testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mode", choices=["inject", "restore"], required=True,
                        help="'inject' to add test data, 'restore' to remove it")
    parser.add_argument("--region", default="FR",
                        help="Region code_insee (default: FR). Required for inject.")
    parser.add_argument("--alert-type", choices=["under_production", "over_production"],
                        default="under_production",
                        help="Alert type to simulate (default: under_production)")
    parser.add_argument("--prod-mw", type=float, default=None,
                        help="Production MW (default: 4000 for under, 8000 for over)")
    parser.add_argument("--conso-mw", type=float, default=None,
                        help="Consumption MW (default: 6000 for under, 5000 for over)")
    args = parser.parse_args(argv)

    conn = None
    try:
        conn = _get_connection()
        if args.mode == "inject":
            defaults = _DEFAULTS[args.alert_type]
            prod_mw = args.prod_mw if args.prod_mw is not None else defaults["prod_mw"]
            conso_mw = args.conso_mw if args.conso_mw is not None else defaults["conso_mw"]
            inject(conn, args.region, args.alert_type, prod_mw, conso_mw)
        else:
            restore(conn)
        return 0
    except Exception as exc:
        logger.error("inject_test_data failed: %s", exc)
        return 1
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
