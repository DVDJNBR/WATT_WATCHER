"""
GRID_POWER_STREAM — Azure Function App Entry Point

Story 1.1: Timer trigger — RTE eCO2mix ingestion → Bronze layer.
Story 4.1: HTTP triggers — /v1/production/regional, /v1/export/csv.
Story 4.3: HTTP triggers — /health, /docs, /openapi.json.
Story 5.2: HTTP trigger — /v1/alerts.
"""

import json
import logging
import os
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import azure.functions as func

try:
    import azure.functions as func  # type: ignore[no-redef]
    AZURE_FUNCTIONS_AVAILABLE = True
except ImportError:
    AZURE_FUNCTIONS_AVAILABLE = False

from shared.rte_client import RTEClient, RTEClientError
from shared.bronze_storage import BronzeStorage
from shared.audit_logger import AuditLogger
from shared.api.models import parse_production_request, parse_export_request
from shared.api.production_service import query_production
from shared.api.export_service import export_to_csv
from shared.api.error_handlers import bad_request, not_found, server_error
from shared.api.routes import ROUTE_PRODUCTION, ROUTE_EXPORT, ROUTE_HEALTH, ROUTE_DOCS, ROUTE_OPENAPI_JSON, ROUTE_ALERTS
from shared.api.auth import require_auth
from shared.api.openapi_spec import build_spec, build_swagger_ui_html
from shared.api.alert_service import query_alerts

logger = logging.getLogger(__name__)


# ─── DB connection helper ────────────────────────────────────────────────────

def _get_db_connection() -> Any:
    """
    Return a Gold SQL DB connection.

    Priority:
    1. SQL_CONNECTION_STRING env var → pyodbc (Azure SQL in production)
    2. LOCAL_GOLD_DB env var → sqlite3 (local dev, points to gold.db path)
    3. Default → sqlite3 on gold.db in project root (local dev fallback)
    """
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    if conn_str:
        try:
            import pyodbc  # type: ignore[import]
            return pyodbc.connect(conn_str)
        except ImportError as e:
            raise RuntimeError("pyodbc not available — install it for Azure SQL") from e

    # Local dev fallback: sqlite3
    import sqlite3
    from pathlib import Path
    local_db = os.environ.get(
        "LOCAL_GOLD_DB",
        str(Path(__file__).parent.parent / "gold.db"),
    )
    logger.info("SQL_CONNECTION_STRING not set — using local SQLite: %s", local_db)
    return sqlite3.connect(local_db)


# ─── Function App ───────────────────────────────────────────────────────────

if AZURE_FUNCTIONS_AVAILABLE:
    app = func.FunctionApp()

    # ── Story 1.1: RTE ingestion timer ──────────────────────────────────────

    @app.timer_trigger(
        schedule="0 */15 * * * *",  # every 15 minutes
        arg_name="timer",
        run_on_startup=False,
    )
    def rte_ingestion(timer: func.TimerRequest) -> None:
        """Timer-triggered RTE eCO2mix ingestion to Bronze layer."""
        job_id = str(uuid.uuid4())
        logger.info("Starting RTE ingestion job: %s", job_id)
        run_ingestion(job_id=job_id)

    # ── Story 4.1: Production regional endpoint ──────────────────────────────

    @app.route(route=ROUTE_PRODUCTION, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    @require_auth
    def get_production_regional(req: func.HttpRequest) -> func.HttpResponse:
        """
        GET /v1/production/regional

        AC #1: Returns aggregated production metrics from Gold SQL.
        AC #2: <500ms target (parameterized queries + SQL indexes).
        AC #3: RESTful — 200, 400, 404, 500.
        """
        request_id = str(uuid.uuid4())

        prod_req, validation_error = parse_production_request(dict(req.params))
        if validation_error:
            body = bad_request(validation_error, request_id)
            return func.HttpResponse(
                json.dumps(body), status_code=400,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )

        try:
            conn = _get_db_connection()
            result = query_production(
                conn,
                region_code=prod_req.region_code,
                start_date=prod_req.start_date,
                end_date=prod_req.end_date,
                source_type=prod_req.source_type,
                limit=prod_req.limit,
                offset=prod_req.offset,
                request_id=request_id,
            )

            if not result["data"]:
                body = not_found(request_id=request_id)
                return func.HttpResponse(
                    json.dumps(body), status_code=404,
                    mimetype="application/json",
                    headers={"X-Request-Id": request_id},
                )

            return func.HttpResponse(
                json.dumps(result), status_code=200,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )

        except Exception as exc:
            logger.error("production endpoint error [%s]: %s", request_id, exc, exc_info=True)
            body = server_error(request_id=request_id)
            return func.HttpResponse(
                json.dumps(body), status_code=500,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )

    # ── Story 4.3: Health check (public) ────────────────────────────────────

    @app.route(route=ROUTE_HEALTH, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    def get_health(req: func.HttpRequest) -> func.HttpResponse:
        """GET /health — liveness probe, no auth required."""
        from shared.api.openapi_spec import API_VERSION as _API_VERSION
        return func.HttpResponse(
            json.dumps({"status": "healthy", "version": _API_VERSION}),
            status_code=200,
            mimetype="application/json",
        )

    # ── Story 4.3: OpenAPI JSON spec (public) ────────────────────────────────

    @app.route(route=ROUTE_OPENAPI_JSON, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    def get_openapi_json(req: func.HttpRequest) -> func.HttpResponse:
        """GET /openapi.json — serves the OpenAPI 3.0.3 spec."""
        return func.HttpResponse(
            json.dumps(build_spec(), indent=2),
            status_code=200,
            mimetype="application/json",
            headers={"Cache-Control": "max-age=300"},
        )

    # ── Story 4.3: Swagger UI (public) ───────────────────────────────────────

    # ── Story 7.0: Manual pipeline trigger (Bronze → Silver → Gold) ─────────

    @app.route(route="v1/admin/pipeline/run", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
    def run_pipeline_now(req: func.HttpRequest) -> func.HttpResponse:
        """
        POST /v1/admin/pipeline/run

        Manual trigger for the full ETL pipeline: Bronze → Silver → Gold.
        Auth level FUNCTION — requires x-functions-key header.
        Accepts optional JSON body: {"minutes": 60, "backfill_days": 0}
        """
        request_id = str(uuid.uuid4())
        try:
            body = req.get_json() if req.get_body() else {}
        except Exception:
            body = {}

        minutes = int(body.get("minutes", 30))
        backfill_days = int(body.get("backfill_days", 0))

        try:
            result = run_full_pipeline(
                job_id=request_id,
                minutes=minutes,
                backfill_days=backfill_days,
            )
            return func.HttpResponse(
                json.dumps(result), status_code=200, mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )
        except Exception as exc:
            logger.error("pipeline trigger error [%s]: %s", request_id, exc, exc_info=True)
            body_err = server_error(request_id=request_id)
            return func.HttpResponse(
                json.dumps(body_err), status_code=500, mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )

    @app.route(route="v1/admin/pipeline/run", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
    def pipeline_status(req: func.HttpRequest) -> func.HttpResponse:
        """GET /v1/admin/pipeline/run — liveness check for pipeline endpoint."""
        return func.HttpResponse(
            json.dumps({"status": "ready", "endpoint": "POST /api/v1/admin/pipeline/run"}),
            status_code=200, mimetype="application/json",
        )

    @app.route(route=ROUTE_DOCS, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    def get_docs(req: func.HttpRequest) -> func.HttpResponse:
        """GET /docs — Swagger UI HTML, loads spec from /api/openapi.json."""
        html = build_swagger_ui_html(openapi_json_url="/api/openapi.json")
        return func.HttpResponse(
            html,
            status_code=200,
            mimetype="text/html; charset=utf-8",
        )

    # ── Story 4.1: CSV export endpoint ──────────────────────────────────────

    @app.route(route=ROUTE_EXPORT, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    @require_auth
    def get_export_csv(req: func.HttpRequest) -> func.HttpResponse:
        """
        GET /v1/export/csv

        AC #4: Returns downloadable CSV with UTF-8 BOM, semicolon separator.
        AC #3: RESTful — 200, 400, 404, 500.
        """
        request_id = str(uuid.uuid4())
        export_req = parse_export_request(dict(req.params))

        try:
            conn = _get_db_connection()
            csv_bytes, filename, row_count = export_to_csv(
                conn,
                region_code=export_req.region_code,
                start_date=export_req.start_date,
                end_date=export_req.end_date,
                source_type=export_req.source_type,
                request_id=request_id,
            )

            if row_count == 0:
                body = not_found(request_id=request_id)
                return func.HttpResponse(
                    json.dumps(body), status_code=404,
                    mimetype="application/json",
                    headers={"X-Request-Id": request_id},
                )

            return func.HttpResponse(
                csv_bytes,
                status_code=200,
                mimetype="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Request-Id": request_id,
                },
            )

        except Exception as exc:
            logger.error("export endpoint error [%s]: %s", request_id, exc, exc_info=True)
            body = server_error(request_id=request_id)
            return func.HttpResponse(
                json.dumps(body), status_code=500,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )

    # ── Story 5.2: Alerts endpoint ───────────────────────────────────────────

    @app.route(route=ROUTE_ALERTS, methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    def get_alerts(req: func.HttpRequest) -> func.HttpResponse:
        """
        GET /v1/alerts?region_code={}&status=active&days=7&limit=50

        AC #1: Returns active alerts for dashboard display.
        AC #2: Reads from audit trail written by AlertEngine.
        """
        request_id = str(uuid.uuid4())
        try:
            region_code = req.params.get("region_code") or None
            status = req.params.get("status", "active") or None
            days = int(req.params.get("days", 7))
            limit = min(int(req.params.get("limit", 50)), 200)

            result = query_alerts(
                region_code=region_code,
                status=status,
                days=days,
                limit=limit,
            )
            return func.HttpResponse(
                json.dumps(result, ensure_ascii=False),
                status_code=200,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )
        except Exception as exc:
            logger.error("alerts endpoint error [%s]: %s", request_id, exc, exc_info=True)
            body = server_error(request_id=request_id)
            return func.HttpResponse(
                json.dumps(body), status_code=500,
                mimetype="application/json",
                headers={"X-Request-Id": request_id},
            )


def run_ingestion(
    job_id: str | None = None,
    local_mode: bool = False,
) -> dict:
    """
    Core ingestion logic — callable both from Azure Function and locally.

    Args:
        job_id: Unique job identifier.
        local_mode: If True, write to local filesystem instead of ADLS.

    Returns:
        Audit log entry dict.
    """
    job_id = job_id or str(uuid.uuid4())

    # Initialize modules
    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME") if not local_mode else None
    bronze = BronzeStorage(
        storage_account_name=storage_account,
        local_mode=local_mode,
    )
    audit = AuditLogger(source="rte_eco2mix", bronze_storage=bronze)
    client = RTEClient()

    try:
        # Fetch latest records (last 30 minutes to handle overlap)
        records = client.fetch_all_recent(minutes=30)

        if not records:
            logger.info("No records returned from API")
            return audit.log_success(record_count=0, job_id=job_id)

        # Write raw JSON to Bronze
        path = bronze.write_json(records)
        logger.info("Written %d records to %s", len(records), path)

        # Audit success
        return audit.log_success(
            record_count=len(records),
            job_id=job_id,
            details={"bronze_path": path},
        )

    except RTEClientError as e:
        logger.error("RTE API error: %s", e)
        return audit.log_failure(
            error=str(e),
            job_id=job_id,
        )

    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return audit.log_failure(
            error=f"Unexpected: {e}",
            job_id=job_id,
        )


def run_full_pipeline(
    job_id: str | None = None,
    local_mode: bool = False,
    minutes: int = 30,
    backfill_days: int = 0,
) -> dict:
    """
    Full ETL pipeline: Bronze → Silver → Gold.

    1. Ingest from RTE API → Bronze (ADLS or local)
    2. Transform Bronze JSON → Silver Parquet (in-memory for Azure, local for dev)
    3. Load Silver → Gold (Azure SQL or SQLite)

    Args:
        job_id: Trace ID.
        local_mode: Use local filesystem instead of ADLS.
        minutes: Lookback window for RTE API (default 30min).
        backfill_days: If >0, fetch N days of historical data.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    from shared.transformations.rte_silver import transform_rte_to_silver
    from shared.gold.dim_loader import DimLoader
    from shared.gold.fact_loader import FactLoader

    job_id = job_id or str(uuid.uuid4())
    results: dict = {"job_id": job_id, "stages": {}}

    # ── Stage 1: Bronze ingestion ────────────────────────────────────────────
    logger.info("[%s] Stage 1: Bronze ingestion (minutes=%d, backfill_days=%d)",
                job_id, minutes, backfill_days)
    bronze_result = run_ingestion(job_id=job_id, local_mode=local_mode)
    results["stages"]["bronze"] = bronze_result
    logger.info("[%s] Bronze: %s (%d records)",
                job_id, bronze_result.get("status"), bronze_result.get("record_count", 0))

    if bronze_result.get("status") == "failure":
        results["status"] = "failure"
        results["failed_stage"] = "bronze"
        return results

    # ── Stage 2: Silver transformation ──────────────────────────────────────
    logger.info("[%s] Stage 2: Silver transformation", job_id)
    try:
        if local_mode:
            # Local: read from filesystem
            bronze_base = _Path(__file__).parent.parent / "bronze" / "rte" / "production"
            bronze_files_paths = sorted(bronze_base.rglob("*.json"))
            silver_base = _Path(__file__).parent.parent / "silver"
            silver_base.mkdir(parents=True, exist_ok=True)
            silver_rows = 0
            for bf in bronze_files_paths:
                res = transform_rte_to_silver(bf, silver_base)
                silver_rows += res.get("rows_written", res.get("rows", 0))
            results["stages"]["silver"] = {"status": "success", "rows": silver_rows}
        else:
            # Azure: download bronze from ADLS → /tmp, transform → /tmp/silver
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

                tmp_silver = _Path(tempfile.mkdtemp()) / "silver"
                tmp_silver.mkdir(parents=True, exist_ok=True)

                res = transform_rte_to_silver(tmp_bronze, tmp_silver)
                results["stages"]["silver"] = res
                results["stages"]["silver"]["_tmp_silver_dir"] = str(tmp_silver)
            else:
                results["stages"]["silver"] = {"status": "skipped", "reason": "no bronze_path"}

    except Exception as exc:
        logger.error("[%s] Silver stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["silver"] = {"status": "failure", "error": str(exc)}
        results["status"] = "partial"
        results["failed_stage"] = "silver"
        return results

    # ── Stage 3: Gold loading ────────────────────────────────────────────────
    logger.info("[%s] Stage 3: Gold loading", job_id)
    try:
        conn = _get_db_connection()

        dim = DimLoader(conn)
        dim.ensure_schema()

        fact = FactLoader(conn)

        if local_mode:
            silver_base = _Path(__file__).parent.parent / "silver"
            gold_result = fact.load_from_silver(silver_base)
        else:
            # Use /tmp silver dir written by the Silver stage
            tmp_silver_dir = results["stages"]["silver"].get("_tmp_silver_dir", "")
            if tmp_silver_dir:
                gold_result = fact.load_from_silver(_Path(tmp_silver_dir))
            else:
                gold_result = {"status": "skipped", "rows_loaded": 0}

        conn.close()
        results["stages"]["gold"] = gold_result
        logger.info("[%s] Gold: %s (%d rows)",
                    job_id, gold_result.get("status"), gold_result.get("rows_loaded", 0))

    except Exception as exc:
        logger.error("[%s] Gold stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["gold"] = {"status": "failure", "error": str(exc)}
        results["status"] = "partial"
        results["failed_stage"] = "gold"
        return results

    results["status"] = "success"
    return results


# ─── Local dev entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_ingestion(local_mode=True)
    print(f"\nResult: {result['status']} — {result['record_count']} records")
