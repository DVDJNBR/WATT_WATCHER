"""
Price Retention — daily purge of FACT_MARKET_PRICE beyond the retention window.

FACT_MARKET_PRICE is refreshed every 15 minutes and only serves the live
dashboard / threshold-calibration use case, not long-term historical
analysis (ENTSO-E itself remains the durable source of truth for that,
queried directly when a fresh calibration is needed — see
docs/entsoe_price_integration_report.md). Keeping only a rolling window
bounds table growth without touching DIM_TIME, which other fact tables
(FACT_ENERGY_FLOW, FACT_METEO, ...) still reference.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 7


def purge_old_prices(db_connection: Any, retention_days: int | None = None) -> int:
    """
    Delete FACT_MARKET_PRICE rows older than the retention window.

    Only deletes from FACT_MARKET_PRICE — DIM_TIME rows are left untouched
    since other fact tables still reference them.

    Args:
        db_connection: Any DB connection with cursor() support.
        retention_days: Override for PRICE_RETENTION_DAYS (mainly for tests).

    Returns:
        Number of rows deleted.
    """
    retention_days = retention_days if retention_days is not None else int(
        os.environ.get("PRICE_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    is_sqlite = isinstance(db_connection, sqlite3.Connection)

    cursor = db_connection.cursor()
    if is_sqlite:
        cursor.execute(
            """DELETE FROM FACT_MARKET_PRICE
               WHERE id_date IN (
                   SELECT id_date FROM DIM_TIME WHERE horodatage < ?
               )""",
            (cutoff.isoformat(),),
        )
    else:
        cursor.execute(
            """DELETE FROM fact_market_price
               WHERE id_date IN (
                   SELECT id_date FROM dim_time WHERE horodatage < %s
               )""",
            (cutoff,),
        )
    deleted = cursor.rowcount
    db_connection.commit()

    logger.info(
        "Price retention: purged %d rows older than %d days (cutoff=%s)",
        deleted, retention_days, cutoff.isoformat(),
    )
    return deleted
