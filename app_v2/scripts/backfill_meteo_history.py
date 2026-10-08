"""
One-off backfill of Open-Meteo Archive history into fact_meteo.

Standalone, on-demand script — deliberately NOT an Azure Function / pipeline
stage. Same Bronze (raw JSON) -> Silver (Parquet) -> Gold (fact_meteo) path
as the live 15-minute meteo_stage (shared.stages.meteo_stage.load_meteo_records),
just fed from the Archive API's historical records instead of the forecast
API's past_days<=7 window.

Why this exists: meteo_stage only ever fetches past_days=3 per run, so
fact_meteo otherwise only accumulates history from whenever the 15-minute
timer first started running continuously — unlike fact_energy_flow (RTE),
météo had zero backfill path at all, so any date range requested before the
pipeline had been running long enough (e.g. a "3 months" frontend view)
shows power data but no météo.

Real ceiling on how far back this can reach: Open-Meteo's Archive API is
ERA5 reanalysis, which typically lags ~5 days behind present. Don't request
end_date closer than that to today — those last few days still need the
live forecast endpoint (meteo_stage's normal 15-min run).

Usage:
    uv run python scripts/backfill_meteo_history.py
    uv run python scripts/backfill_meteo_history.py --local          # local_mode
    uv run python scripts/backfill_meteo_history.py --days-back 120  # wider net
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from shared.bronze_storage import BronzeStorage
from shared.silver_storage import SilverStorage
from shared.stages import meteo_stage

logger = logging.getLogger(__name__)

ARCHIVE_LAG_DAYS = 5  # ERA5 reanalysis latency; stay clear of "today"


def main():
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local", action="store_true",
        help="local_mode: local blob folders + SQLite, instead of the real "
             "storage account + Supabase.",
    )
    parser.add_argument(
        "--days-back", type=int, default=90,
        help="How many days of history to request, ending ARCHIVE_LAG_DAYS "
             "days before today (the Archive API can't yet see more recent "
             "than that). Default 90 covers the '3 months' frontend view.",
    )
    args = parser.parse_args()

    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME") if not args.local else None
    bronze = BronzeStorage(storage_account_name=storage_account, local_mode=args.local)
    silver = SilverStorage(storage_account_name=storage_account, local_mode=args.local)

    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=ARCHIVE_LAG_DAYS)
    start_date = end_date - timedelta(days=args.days_back)

    logger.info(
        "Backfilling météo Archive history: %s to %s (%d days)",
        start_date, end_date, args.days_back,
    )

    from shared.open_meteo_client import fetch_meteo_archive_all_regions
    meteo_records = fetch_meteo_archive_all_regions(
        start_date=start_date.isoformat(), end_date=end_date.isoformat(),
    )

    result = meteo_stage.load_meteo_records(
        job_id="backfill_meteo_history", bronze=bronze, silver=silver,
        meteo_records=meteo_records,
    )
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
