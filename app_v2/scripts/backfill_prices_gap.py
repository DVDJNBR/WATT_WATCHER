"""
Backfill fact_market_price for the gap caused by the _parse_price_document
namespace bug (pinned ns: URI silently returned [] when ENTSO-E changed the
document namespace — pipeline appeared healthy but wrote 0 rows every day).

Gap: ~2026-08-19 to 2026-09-30 (~6 weeks, ~1032 rows at PT15M resolution).

This calls the exact same price_stage.run() the daily pipeline calls — same
Bronze/Silver/Gold path, same ON CONFLICT(id_date) DO UPDATE — so it is safe
to run multiple times and safe to run while the live pipeline is active.

Usage:
    cd app_v2
    export ENTSOE_API_TOKEN=<token>
    export SUPABASE_CONNECTION_STRING=<dsn>
    uv run python scripts/backfill_prices_gap.py

Or, if .env is present:
    uv run --env-file .env python scripts/backfill_prices_gap.py

CI: added as a GitHub Actions workflow step that runs on push when a gap is
detected (see .github/workflows/backfill_prices.yml).
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

# Gap start: day after last known good row in fact_market_price.
# Set conservatively to 2026-08-19 00:00 UTC (10 days before the confirmed
# last-row date of 2026-08-28 to catch any partial days).
GAP_START = datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    if not os.environ.get("ENTSOE_API_TOKEN"):
        raise SystemExit(
            "ENTSOE_API_TOKEN not set — export it or run with --env-file .env"
        )

    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME")
    local_mode = storage_account is None

    from shared.bronze_storage import BronzeStorage
    from shared.silver_storage import SilverStorage
    from shared.stages import price_stage

    bronze = BronzeStorage(storage_account_name=storage_account, local_mode=local_mode)
    silver = SilverStorage(storage_account_name=storage_account, local_mode=local_mode)

    period_end = datetime.now(timezone.utc)
    logger.info("Backfilling prices %s → %s", GAP_START.date(), period_end.date())

    result = price_stage.run(
        job_id="backfill_prices_gap",
        bronze=bronze,
        silver=silver,
        period_start=GAP_START,
        period_end=period_end,
    )
    logger.info("Result: %s", result)

    if result.get("status") not in ("success", "empty"):
        raise SystemExit(f"Backfill failed: {result}")


if __name__ == "__main__":
    main()
