"""
One-off backfill of ENTSO-E cross-border physical flow into fact_cross_border_flow.

Same seed-then-automate pattern as backfill_market_prices.py: calls the exact
same shared.stages.cross_border_stage.run() the automated pipeline_daily
timer calls, just with a wider period_start/period_end, through the same
Bronze -> Silver -> Gold path.

Window is intentionally 35 days, not "since the beginning of fact_energy_flow"
like the price backfill: each day costs 8 ENTSO-E requests (4 borders x 2
directions), so backfilling months of history in one unsupervised run risks
a very long run against a rate-limited external API for marginal benefit —
35 days is enough to fill the dashboard's "Mois" period view with real data.
Extend --days if more history is wanted later.

Usage:
    uv run python scripts/backfill_cross_border_flow.py
    uv run python scripts/backfill_cross_border_flow.py --local --days 60
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from shared.bronze_storage import BronzeStorage
from shared.db import get_db_connection
from shared.silver_storage import SilverStorage
from shared.stages import cross_border_stage

logger = logging.getLogger(__name__)


def main():
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local", action="store_true",
        help="local_mode: SQLite (LOCAL_GOLD_DB or ./gold.db) + local blob folders.",
    )
    parser.add_argument("--days", type=int, default=35, help="How many days of history to backfill (default 35).")
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
    finally:
        conn.close()

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=args.days)
    logger.info("Backfilling ENTSO-E cross-border flow %s -> %s (%d days)", period_start, period_end, args.days)

    result = cross_border_stage.run(
        job_id="backfill_cross_border_flow", bronze=bronze, silver=silver,
        period_start=period_start, period_end=period_end,
    )
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
