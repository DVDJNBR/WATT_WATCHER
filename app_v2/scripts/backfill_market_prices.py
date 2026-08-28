"""
One-off backfill of ENTSO-E day-ahead prices into fact_market_price — FT/PRICES follow-up.

Standalone, on-demand script — deliberately NOT an Azure Function / pipeline
stage, but NOT a separate write path either: this calls the exact same
shared.stages.price_stage.run() the automated pipeline_daily timer calls,
just with a wider period_start/period_end. Same Bronze (raw JSON) -> Silver
(Parquet) -> Gold (fact_market_price) sequence, same idempotent
ON CONFLICT(id_date) DO UPDATE — a manual run is not allowed to diverge from
what the automation would have produced if it had been running all along.

Why this exists: price_stage.py's live 26h lookback would only fill
fact_market_price one day at a time starting from whenever pipeline_daily
first ran. The threshold recalibration this feeds
(docs/entsoe_price_integration_report.md, "Prochaines etapes") needs price
history that already overlaps with fact_energy_flow's RTE history — waiting
months for it to accumulate day-by-day isn't acceptable.

This is the manual half of the project's seed-then-automate pattern: compute
what's worth keeping, do one bulk historical injection through scripts/ by
hand, then hand off to the Azure Functions timers for everything from that
point forward. Keeping that pattern intact (rather than writing straight to
Gold, bypassing Bronze/Silver) is what makes it possible to point a fresh
repo + a fresh Supabase database at this codebase and rebuild the full
history from scratch, not just from whenever the automation happened to
start.

Usage:
    uv run python scripts/backfill_market_prices.py
    uv run python scripts/backfill_market_prices.py --local  # local_mode (SQLite + local blobs)
"""

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from shared.bronze_storage import BronzeStorage
from shared.db import get_db_connection
from shared.silver_storage import SilverStorage
from shared.stages import price_stage

logger = logging.getLogger(__name__)


def _earliest_energy_flow_timestamp(conn) -> datetime:
    """
    fact_energy_flow's earliest timestamp is the real bound on this backfill:
    prices from before RTE production/consumption history exists can never
    be joined against a ratio for the recalibration this feeds.
    """
    cursor = conn.cursor()
    is_sqlite = isinstance(conn, sqlite3.Connection)
    tbl_flow = "FACT_ENERGY_FLOW" if is_sqlite else "fact_energy_flow"
    tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
    cursor.execute(f"""
        SELECT MIN(t.horodatage) FROM {tbl_flow} f JOIN {tbl_time} t ON f.id_date = t.id_date
    """)
    (earliest,) = cursor.fetchone()
    if isinstance(earliest, str):
        earliest = datetime.fromisoformat(earliest)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    return earliest


def main():
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local", action="store_true",
        help="local_mode: SQLite (LOCAL_GOLD_DB or ./gold.db) + local blob folders, "
             "instead of Supabase + the real storage account.",
    )
    args = parser.parse_args()

    if not os.environ.get("ENTSOE_API_TOKEN"):
        raise SystemExit("ENTSOE_API_TOKEN not set — export it or load app_v2/.env first")

    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME") if not args.local else None
    bronze = BronzeStorage(storage_account_name=storage_account, local_mode=args.local)
    silver = SilverStorage(storage_account_name=storage_account, local_mode=args.local)

    conn = get_db_connection()
    try:
        from shared.gold.dim_loader import DimLoader
        DimLoader(conn).ensure_schema()
        period_start = _earliest_energy_flow_timestamp(conn)
    finally:
        conn.close()

    period_end = datetime.now(timezone.utc)
    logger.info("Backfilling ENTSO-E prices %s -> %s", period_start, period_end)

    result = price_stage.run(
        job_id="backfill_market_prices", bronze=bronze, silver=silver,
        period_start=period_start, period_end=period_end,
    )
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
