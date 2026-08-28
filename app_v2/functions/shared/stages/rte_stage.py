"""
RTE eCO2mix stage — the 15-minute pipeline's core: Bronze -> Silver -> Gold
for production/consumption data. The only source with a genuinely persisted
Silver Parquet layer today (see docs/data_model.md); every other stage keeps
its Silver DataFrame in memory and only persists Bronze+Silver as archival
side effects, since their Gold-loading logic doesn't need to re-read them.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from shared.rte_client import RTEClient, RTEClientError
from shared.audit_logger import AuditLogger
from shared.db import get_db_connection

logger = logging.getLogger(__name__)


def _run_bronze_ingestion(bronze: Any, job_id: str, minutes: int) -> dict:
    """Fetch recent RTE records and write them to Bronze. Returns an audit entry."""
    audit = AuditLogger(source="rte_eco2mix", bronze_storage=bronze)
    client = RTEClient()

    try:
        # RTE API has ~2h publication lag, use a wide lookback by default.
        records = client.fetch_all_recent(minutes=minutes)

        if not records:
            logger.info("No records returned from API")
            return audit.log_success(record_count=0, job_id=job_id)

        path = bronze.write_json(records)
        logger.info("Written %d records to %s", len(records), path)

        return audit.log_success(
            record_count=len(records), job_id=job_id, details={"bronze_path": path},
        )

    except RTEClientError as e:
        logger.error("RTE API error: %s", e)
        return audit.log_failure(error=str(e), job_id=job_id)

    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return audit.log_failure(error=f"Unexpected: {e}", job_id=job_id)


def run(
    job_id: str,
    bronze: Any,
    silver: Any,
    local_mode: bool = False,
    minutes: int = 30,
) -> dict:
    """
    Full RTE ETL: Bronze -> Silver -> Gold.

    Args:
        job_id: Trace ID.
        bronze: Shared BronzeStorage instance (already configured for local/ADLS).
        silver: Shared SilverStorage instance (already configured for local/ADLS).
        local_mode: Use local filesystem instead of ADLS for intermediate files.
        minutes: Lookback window for the RTE API fetch.

    Returns:
        {"status": "success"|"failure"|"partial", "stages": {"bronze": ..., "silver": ..., "gold": ...}}
    """
    from shared.transformations.rte_silver import transform_rte_to_silver
    from shared.gold.dim_loader import DimLoader
    from shared.gold.fact_loader import FactLoader

    result: dict = {"stages": {}}

    # ── Bronze ────────────────────────────────────────────────────────────
    logger.info("[%s] RTE: Bronze ingestion (minutes=%d)", job_id, minutes)
    bronze_result = _run_bronze_ingestion(bronze, job_id, minutes)
    result["stages"]["bronze"] = bronze_result
    logger.info("[%s] RTE Bronze: %s (%d records)",
                job_id, bronze_result.get("status"), bronze_result.get("record_count", 0))

    if bronze_result.get("status") == "failure":
        result["status"] = "failure"
        result["failed_stage"] = "bronze"
        return result

    # ── Silver ────────────────────────────────────────────────────────────
    logger.info("[%s] RTE: Silver transformation", job_id)
    try:
        if local_mode:
            bronze_base = Path(__file__).parent.parent.parent.parent / "bronze" / "rte" / "production"
            bronze_files_paths = sorted(bronze_base.rglob("*.json"))
            silver_base = Path(__file__).parent.parent.parent.parent / "silver"
            silver_base.mkdir(parents=True, exist_ok=True)
            silver_rows = 0
            for bf in bronze_files_paths:
                res = transform_rte_to_silver(bf, silver_base)
                silver_rows += res.get("rows_written", res.get("rows", 0))
            result["stages"]["silver"] = {"status": "success", "rows": silver_rows}
        else:
            # Azure: download bronze from ADLS -> /tmp, transform -> /tmp/silver
            bronze_adls_path = bronze_result.get("details", {}).get("bronze_path", "")
            if bronze_adls_path:
                import tempfile
                from azure.identity import DefaultAzureCredential
                from azure.storage.filedatalake import DataLakeServiceClient as _DLClient

                storage_account = os.environ.get("STORAGE_ACCOUNT_NAME", "")
                account_url = f"https://{storage_account}.dfs.core.windows.net"
                svc = _DLClient(account_url=account_url, credential=DefaultAzureCredential())

                # bronze_adls_path = "bronze/rte/production/.../file.json"
                parts = bronze_adls_path.split("/", 1)
                container, file_in_container = parts[0], parts[1]
                fs = svc.get_file_system_client(container)
                bronze_bytes = fs.get_file_client(file_in_container).download_file().readall()

                with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as tf:
                    tf.write(bronze_bytes)
                    tmp_bronze = tf.name

                tmp_silver = Path(tempfile.mkdtemp()) / "silver"
                tmp_silver.mkdir(parents=True, exist_ok=True)

                res = transform_rte_to_silver(tmp_bronze, tmp_silver)
                result["stages"]["silver"] = res
                result["stages"]["silver"]["_tmp_silver_dir"] = str(tmp_silver)

                # transform_rte_to_silver writes under tmp_silver/silver/rte/production/...
                # (it prefixes its own "silver/rte/production" inside the output_dir we
                # gave it) — point upload_directory at that inner folder so the real ADLS
                # "silver" container ends up with a clean rte/production/year=.../ layout,
                # not a doubled silver/silver/... nesting.
                rte_silver_local = tmp_silver / "silver" / "rte" / "production"
                if rte_silver_local.exists():
                    uploaded = silver.upload_directory(rte_silver_local, prefix="rte/production")
                    result["stages"]["silver"]["files_persisted_to_adls"] = uploaded
            else:
                result["stages"]["silver"] = {"status": "skipped", "reason": "no bronze_path"}

    except Exception as exc:
        logger.error("[%s] RTE Silver stage failed: %s", job_id, exc, exc_info=True)
        result["stages"]["silver"] = {"status": "failure", "error": str(exc)}
        result["status"] = "partial"
        result["failed_stage"] = "silver"
        return result

    # ── Gold ──────────────────────────────────────────────────────────────
    logger.info("[%s] RTE: Gold loading", job_id)
    try:
        conn = get_db_connection()

        dim = DimLoader(conn)
        dim.ensure_schema()

        fact = FactLoader(conn)

        if local_mode:
            silver_base = Path(__file__).parent.parent.parent.parent / "silver"
            gold_result = fact.load_from_silver(silver_base)
        else:
            tmp_silver_dir = result["stages"]["silver"].get("_tmp_silver_dir", "")
            if tmp_silver_dir:
                gold_result = fact.load_from_silver(Path(tmp_silver_dir))
            else:
                gold_result = {"status": "skipped", "rows_loaded": 0}

        conn.close()
        result["stages"]["gold"] = gold_result
        logger.info("[%s] RTE Gold: %s (%d rows)",
                    job_id, gold_result.get("status"), gold_result.get("rows_loaded", 0))

    except Exception as exc:
        logger.error("[%s] RTE Gold stage failed: %s", job_id, exc, exc_info=True)
        result["stages"]["gold"] = {"status": "failure", "error": str(exc)}
        result["status"] = "partial"
        result["failed_stage"] = "gold"
        return result

    result["status"] = "success"
    return result
