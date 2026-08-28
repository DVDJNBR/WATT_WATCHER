"""
One-off backfill of RTE eco2mix regional history into fact_energy_flow.

Standalone, on-demand script — deliberately NOT an Azure Function / pipeline
stage. Calls the exact same shared.stages.rte_stage.run() the pipeline_15min
timer calls, just with a much wider lookback (`minutes`) — same Bronze
(raw JSON) -> Silver (Parquet) -> Gold (fact_energy_flow) path either way,
no separate write logic to keep in sync.

Why this exists: pipeline_15min only ever looks back ~30 minutes per run,
so fact_energy_flow otherwise only accumulates history from whenever the
15-minute timer first started running — discovered directly while trying to
recalibrate the surplus/curtailment threshold against real prices
(docs/entsoe_price_integration_report.md): fact_energy_flow turned out to
have only 11 real continuous days of data plus a disconnected 4-day snippet
from a much earlier test run, nowhere near enough to recalibrate anything.

Real ceiling on how far back this can reach: RTE's live "eco2mix-regional-tr"
dataset (the *only* one this client's RTEClient talks to) is "temps réel" —
provisional, rolling-window data, not the multi-year "definitive" archive.
Checked directly against the API (ordering by date_heure ASC, no filter):
the oldest record currently available was from 2026-06-30, i.e. this
dataset only actually retains ~2 months of history at any given time, no
matter how far back --days-back requests. That's still a large improvement
over 11 days, but reproducing the original manual calibration's full year
of 2025 data would need RTE's separate definitive/consolidated dataset —
a different endpoint and likely a different schema, out of scope here.

Usage:
    uv run python scripts/backfill_rte_history.py
    uv run python scripts/backfill_rte_history.py --local          # local_mode
    uv run python scripts/backfill_rte_history.py --days-back 120  # wider net; API
                                                                    # silently returns
                                                                    # whatever it actually has
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from shared.bronze_storage import BronzeStorage
from shared.silver_storage import SilverStorage
from shared.stages import rte_stage

logger = logging.getLogger(__name__)


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
        help="Requested lookback in days. RTE's live dataset only actually "
             "retains a rolling ~2 months regardless of this value — the API "
             "just returns whatever it genuinely has, so this only needs to "
             "be wider than that retention window, not exact.",
    )
    args = parser.parse_args()

    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME") if not args.local else None
    bronze = BronzeStorage(storage_account_name=storage_account, local_mode=args.local)
    silver = SilverStorage(storage_account_name=storage_account, local_mode=args.local)

    minutes = args.days_back * 24 * 60
    logger.info(
        "Backfilling RTE eco2mix history: requested lookback=%d days "
        "(actual result bounded by the API's real retention, not this number)",
        args.days_back,
    )
    logger.info(
        "This paginates the RTE API 100 records/page — likely several hundred "
        "sequential requests. Progress logs every 20 pages; a long quiet "
        "stretch between them is normal, not a hang."
    )

    result = rte_stage.run(
        job_id="backfill_rte_history", bronze=bronze, silver=silver,
        local_mode=args.local, minutes=minutes,
    )
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
