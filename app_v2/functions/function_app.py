"""
WATT_WATCHER — Azure Function App Entry Point (pipeline only)

Three timer triggers, one per real refresh cadence — not one function doing
everything every 15 minutes regardless of whether the underlying data
actually changes that often (that mismatch is what let ODRE's capacity
registry, updated ~once a year, get re-fetched 96x/day unnoticed for a
while). Each stage's actual fetch/clean/load logic lives in its own module
under shared/stages/ — this file only wires timers to stages.

- pipeline_15min  : RTE eCO2mix (production/consumption) + Open-Meteo —
                    the two sources that genuinely change continuously.
- pipeline_daily  : ENTSO-E day-ahead prices + ENTSO-E generation outages —
                    both published once a day, checking more often gains
                    nothing.
- pipeline_weekly : ODRE installed-capacity registry — changes ~yearly,
                    weekly is a comfortable margin, not a requirement.

The dashboard/API that reads this data lives separately in api/ (FastAPI,
deployed on the VPS).
"""

import logging
import os
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import azure.functions as func

try:
    import azure.functions as func  # type: ignore[no-redef]
    AZURE_FUNCTIONS_AVAILABLE = True
except ImportError:
    AZURE_FUNCTIONS_AVAILABLE = False

from shared.bronze_storage import BronzeStorage
from shared.silver_storage import SilverStorage
from shared.db import get_db_connection
from shared.stages import rte_stage, meteo_stage, capacity_stage, price_stage, outages_stage

logger = logging.getLogger(__name__)


def _storages(local_mode: bool) -> tuple[BronzeStorage, SilverStorage]:
    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME") if not local_mode else None
    return (
        BronzeStorage(storage_account_name=storage_account, local_mode=local_mode),
        SilverStorage(storage_account_name=storage_account, local_mode=local_mode),
    )


def run_15min_pipeline(job_id: str | None = None, local_mode: bool = False, minutes: int = 30) -> dict:
    """RTE production + Open-Meteo — the sources that change continuously."""
    job_id = job_id or str(uuid.uuid4())
    results: dict = {"job_id": job_id, "stages": {}}
    bronze, silver = _storages(local_mode)

    rte_result = rte_stage.run(job_id, bronze, silver, local_mode=local_mode, minutes=minutes)
    results["stages"]["rte"] = rte_result
    if rte_result.get("status") == "failure":
        results["status"] = "failure"
        results["failed_stage"] = "rte"
        return results

    results["stages"]["meteo"] = meteo_stage.run(job_id, bronze, silver)
    results["status"] = "success"
    return results


def run_daily_pipeline(job_id: str | None = None, local_mode: bool = False) -> dict:
    """ENTSO-E prices + ENTSO-E outages — both published once a day."""
    job_id = job_id or str(uuid.uuid4())
    results: dict = {"job_id": job_id, "stages": {}}
    bronze, silver = _storages(local_mode)

    results["stages"]["price"] = price_stage.run(job_id, bronze, silver)
    results["stages"]["outages"] = outages_stage.run(job_id, bronze, silver)
    results["status"] = "success"
    return results


def run_weekly_pipeline(job_id: str | None = None, local_mode: bool = False) -> dict:
    """ODRE installed capacity — changes ~once a year."""
    job_id = job_id or str(uuid.uuid4())
    results: dict = {"job_id": job_id, "stages": {}}
    bronze, silver = _storages(local_mode)

    results["stages"]["capacity"] = capacity_stage.run(job_id, bronze, silver)
    results["status"] = "success"
    return results


# ─── Function App ───────────────────────────────────────────────────────────

if AZURE_FUNCTIONS_AVAILABLE:
    app = func.FunctionApp()

    @app.timer_trigger(
        schedule="0 */15 * * * *",  # every 15 minutes
        arg_name="timer",
        run_on_startup=False,
    )
    def pipeline_15min(timer: func.TimerRequest) -> None:
        """RTE eCO2mix + Open-Meteo -> Bronze -> Silver -> Gold."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] pipeline_15min starting", job_id)
        run_15min_pipeline(job_id=job_id, minutes=240)

    @app.timer_trigger(
        schedule="0 0 6 * * *",  # every day at 06:00 UTC
        arg_name="timer",
        run_on_startup=False,
    )
    def pipeline_daily(timer: func.TimerRequest) -> None:
        """ENTSO-E prices + ENTSO-E outages -> Bronze -> Silver -> Gold."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] pipeline_daily starting", job_id)
        run_daily_pipeline(job_id=job_id)

    @app.timer_trigger(
        schedule="0 0 3 * * 0",  # every Sunday at 03:00 UTC
        arg_name="timer",
        run_on_startup=False,
    )
    def pipeline_weekly(timer: func.TimerRequest) -> None:
        """ODRE installed capacity -> Bronze -> Silver -> Gold."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] pipeline_weekly starting", job_id)
        run_weekly_pipeline(job_id=job_id)

    # ── SQL reference snapshot timer ─────────────────────────────────────────

    @app.timer_trigger(
        schedule="0 0 1 * * *",  # every day at 01:00 UTC
        arg_name="timer",
        run_on_startup=False,
    )
    def sql_reference_snapshot_timer(timer: func.TimerRequest) -> None:
        """Daily snapshot of SQL reference tables (DIM_REGION, DIM_SOURCE) → Bronze layer."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] SQL reference snapshot starting", job_id)
        storage_account = os.environ.get("STORAGE_ACCOUNT_NAME")
        bronze = BronzeStorage(storage_account_name=storage_account)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            snapshot = {}
            for table in ("DIM_REGION", "DIM_SOURCE"):
                cursor.execute(f"SELECT * FROM {table}")  # noqa: S608
                cols = [col[0] for col in cursor.description]
                snapshot[table] = [dict(zip(cols, row)) for row in cursor.fetchall()]
            path = bronze.write_json(snapshot, source="infra")
            logger.info("[%s] SQL snapshot written → %s", job_id, path)
        except Exception as exc:
            logger.error("[%s] SQL snapshot failed: %s", job_id, exc, exc_info=True)
        finally:
            if conn:
                conn.close()


# ─── Local dev entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_15min_pipeline(local_mode=True)
    print(f"\nResult: {result['status']}")
