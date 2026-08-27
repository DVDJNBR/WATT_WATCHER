"""
WATT_WATCHER — Azure Function App Entry Point (pipeline only)

Ingests RTE eCO2mix, Météo-France, ODRE capacity, and grid maintenance data
on a schedule and loads it into Supabase (Gold layer). The dashboard/API that
reads this data lives separately in api/ (FastAPI, deployed on the VPS).
"""

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
from shared.maintenance_scraper import MaintenanceScraper
from shared.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


# ─── DB connection helper ────────────────────────────────────────────────────

def _get_db_connection() -> Any:
    """
    Return a Gold SQL DB connection.

    Priority:
    1. SUPABASE_CONNECTION_STRING env var → psycopg2 (Supabase/PostgreSQL in production)
    2. LOCAL_GOLD_DB env var → sqlite3 (local dev, points to gold.db path)
    3. Default → sqlite3 on gold.db in project root (local dev fallback)
    """
    db_url = os.environ.get("SUPABASE_CONNECTION_STRING", "")
    if db_url:
        try:
            import psycopg2  # type: ignore[import]
            from urllib.parse import urlparse, unquote
            # Parse manually — libpq truncates usernames containing dots (Supabase pooler issue)
            p = urlparse(db_url)
            return psycopg2.connect(
                host=p.hostname,
                port=p.port or 5432,
                dbname=(p.path or '/postgres').lstrip('/'),
                user=unquote(p.username or ''),
                password=unquote(p.password or ''),
                sslmode='require',
            )
        except ImportError as e:
            raise RuntimeError("psycopg2 not available — install psycopg2-binary") from e

    # Local dev fallback: sqlite3
    import sqlite3
    from pathlib import Path
    local_db = os.environ.get(
        "LOCAL_GOLD_DB",
        str(Path(__file__).parent.parent / "gold.db"),
    )
    logger.info("SUPABASE_CONNECTION_STRING not set — using local SQLite: %s", local_db)
    return sqlite3.connect(local_db)


# ─── Function App ───────────────────────────────────────────────────────────

if AZURE_FUNCTIONS_AVAILABLE:
    app = func.FunctionApp()

    # ── RTE ingestion timer ──────────────────────────────────────────────────

    @app.timer_trigger(
        schedule="0 */15 * * * *",  # every 15 minutes
        arg_name="timer",
        run_on_startup=False,
    )
    def rte_ingestion(timer: func.TimerRequest) -> None:
        """Timer-triggered full pipeline run: RTE/Météo/ODRE Bronze → Silver → Gold (Supabase)."""
        job_id = str(uuid.uuid4())
        logger.info("Starting pipeline job: %s", job_id)
        run_full_pipeline(job_id=job_id, minutes=240)

    # ── Maintenance scraping timer ───────────────────────────────────────────

    @app.timer_trigger(
        schedule="0 0 6 * * *",  # every day at 06:00 UTC
        arg_name="timer",
        run_on_startup=False,
    )
    def maintenance_scraping_timer(timer: func.TimerRequest) -> None:
        """Daily scraping of grid maintenance events → Bronze layer."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] Maintenance scraping starting", job_id)
        storage_account = os.environ.get("STORAGE_ACCOUNT_NAME")
        bronze = BronzeStorage(storage_account_name=storage_account)
        scraper = MaintenanceScraper(
            base_url=os.environ.get("MAINTENANCE_SCRAPING_URL")
        )
        try:
            records = scraper.scrape_from_url()
            path = bronze.write_json(records, source="maintenance")
            logger.info("[%s] Scraped %d maintenance events → %s", job_id, len(records), path)
        except Exception as exc:
            logger.error("[%s] Maintenance scraping failed: %s", job_id, exc, exc_info=True)

    # ── Price retention timer ────────────────────────────────────────────────

    @app.timer_trigger(
        schedule="0 15 2 * * *",  # every day at 02:15 UTC
        arg_name="timer",
        run_on_startup=False,
    )
    def price_retention_timer(timer: func.TimerRequest) -> None:
        """Daily purge of FACT_MARKET_PRICE rows older than PRICE_RETENTION_DAYS."""
        job_id = str(uuid.uuid4())
        logger.info("[%s] Price retention starting", job_id)
        conn = None
        try:
            from shared.price_retention import purge_old_prices
            conn = _get_db_connection()
            deleted = purge_old_prices(conn)
            logger.info("[%s] Price retention: purged %d rows", job_id, deleted)
        except Exception as exc:
            logger.error("[%s] Price retention failed: %s", job_id, exc, exc_info=True)
        finally:
            if conn:
                conn.close()

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
            conn = _get_db_connection()
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


def run_ingestion(
    job_id: str | None = None,
    local_mode: bool = False,
    minutes: int = 240,
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
        # Fetch latest records — RTE API has ~2h lag, use 240 min default
        records = client.fetch_all_recent(minutes=minutes)

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
    3. Load Silver → Gold (Supabase or SQLite)

    Args:
        job_id: Trace ID.
        local_mode: Use local filesystem instead of ADLS.
        minutes: Lookback window for RTE API (default 30min).
        backfill_days: If >0, fetch N days of historical data.
    """
    from pathlib import Path as _Path
    from shared.transformations.rte_silver import transform_rte_to_silver
    from shared.gold.dim_loader import DimLoader
    from shared.gold.fact_loader import FactLoader

    job_id = job_id or str(uuid.uuid4())
    results: dict = {"job_id": job_id, "stages": {}}

    # ── Stage 1: Bronze ingestion ────────────────────────────────────────────
    logger.info("[%s] Stage 1: Bronze ingestion (minutes=%d, backfill_days=%d)",
                job_id, minutes, backfill_days)
    bronze_result = run_ingestion(job_id=job_id, local_mode=local_mode, minutes=minutes)
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

    # ── Stage 4: Météo (Open-Meteo) — non-fatal ───────────────────────────────
    logger.info("[%s] Stage 4: Météo ingestion", job_id)
    try:
        from shared.open_meteo_client import fetch_meteo_all_regions, REGION_CENTROIDS
        from shared.transformations.meteo_silver import transform_meteo_to_silver
        from shared.gold.dim_loader import DimLoader as _DimLoader

        meteo_records = fetch_meteo_all_regions(past_days=3)
        df_meteo = transform_meteo_to_silver(meteo_records)

        if df_meteo.empty:
            results["stages"]["meteo"] = {"status": "empty", "rows": 0}
        else:
            conn_m = _get_db_connection()
            try:
                dim_m = _DimLoader(conn_m)
                dim_m.ensure_schema()
                # Upsert regions from centroids
                dim_m.upsert_regions([
                    {"code_insee": code, "nom_region": info["name"]}
                    for code, info in REGION_CENTROIDS.items()
                ])
                # Upsert timestamps
                timestamps_m = df_meteo["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:00").tolist()
                dim_m.upsert_time(timestamps_m)

                import sqlite3 as _sqlite3_m
                is_sqlite_m = isinstance(conn_m, _sqlite3_m.Connection)
                ph_m = "?" if is_sqlite_m else "%s"
                tbl_mt = "FACT_METEO" if is_sqlite_m else "fact_meteo"
                tbl_dt = "DIM_TIME"   if is_sqlite_m else "dim_time"
                tbl_dr = "DIM_REGION" if is_sqlite_m else "dim_region"

                cursor_m = conn_m.cursor()
                rows_loaded_m = 0
                for _, row in df_meteo.iterrows():
                    ts_str = row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")  # type: ignore
                    cursor_m.execute(
                        f"SELECT id_date FROM {tbl_dt} WHERE horodatage = {ph_m}", (ts_str,)
                    )
                    id_date_r = cursor_m.fetchone()
                    cursor_m.execute(
                        f"SELECT id_region FROM {tbl_dr} WHERE code_insee = {ph_m}", (row["region_code"],)
                    )
                    id_region_r = cursor_m.fetchone()
                    if not id_date_r or not id_region_r:
                        continue
                    _cloud = row.get("cloudcover_pct")
                    _cloud = float(_cloud) if _cloud is not None and _cloud == _cloud else None
                    if is_sqlite_m:
                        cursor_m.execute(
                            f"""INSERT INTO {tbl_mt} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(id_date, id_region) DO UPDATE SET
                                    temperature_c  = excluded.temperature_c,
                                    wind_speed_10m = excluded.wind_speed_10m,
                                    cloudcover_pct = excluded.cloudcover_pct""",
                            (id_date_r[0], id_region_r[0], row["temperature_c"], row.get("wind_speed_10m"), _cloud),
                        )
                    else:
                        cursor_m.execute(
                            f"""INSERT INTO {tbl_mt} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (id_date, id_region) DO UPDATE SET
                                    temperature_c  = EXCLUDED.temperature_c,
                                    wind_speed_10m = EXCLUDED.wind_speed_10m,
                                    cloudcover_pct = EXCLUDED.cloudcover_pct""",
                            (id_date_r[0], id_region_r[0], row["temperature_c"], row.get("wind_speed_10m"), _cloud),
                        )
                    rows_loaded_m += 1
                    if rows_loaded_m % 500 == 0:
                        conn_m.commit()
                conn_m.commit()
                results["stages"]["meteo"] = {"status": "success", "rows": rows_loaded_m}
                logger.info("[%s] Météo: %d rows loaded", job_id, rows_loaded_m)
            finally:
                conn_m.close()

    except Exception as exc:
        logger.error("[%s] Météo stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["meteo"] = {"status": "failure", "error": str(exc)}

    # ── Stage 5: Capacité installée (ODRE) — non-fatal ────────────────────────
    logger.info("[%s] Stage 5: Capacity ingestion (ODRE)", job_id)
    try:
        from shared.odre_capacity_client import fetch_capacity
        from shared.gold.dim_loader import DimLoader as _DimLoader2

        capacity_records = fetch_capacity()

        if not capacity_records:
            results["stages"]["capacity"] = {"status": "empty", "rows": 0}
        else:
            conn_c = _get_db_connection()
            try:
                dim_c = _DimLoader2(conn_c)
                dim_c.ensure_schema()
                dim_c.upsert_sources()

                # Upsert regions from capacity records
                regions_c = {}
                for rec in capacity_records:
                    code = rec.get("region_code")
                    name = rec.get("region_name")
                    if code and name and code not in regions_c:
                        regions_c[code] = name
                if regions_c:
                    dim_c.upsert_regions([
                        {"code_insee": code, "nom_region": name}
                        for code, name in regions_c.items()
                    ])

                import sqlite3 as _sqlite3_c
                is_sqlite_c = isinstance(conn_c, _sqlite3_c.Connection)
                ph_c = "?" if is_sqlite_c else "%s"
                tbl_cap = "FACT_CAPACITY" if is_sqlite_c else "fact_capacity"
                tbl_reg = "DIM_REGION"    if is_sqlite_c else "dim_region"
                tbl_src = "DIM_SOURCE"    if is_sqlite_c else "dim_source"

                cursor_c = conn_c.cursor()
                rows_loaded_c = 0
                for rec in capacity_records:
                    code = rec.get("region_code")
                    source = rec.get("source_name")
                    puissance = rec.get("puissance_installee_mw")
                    annee = rec.get("annee")
                    if not code or not source:
                        continue
                    cursor_c.execute(
                        f"SELECT id_region FROM {tbl_reg} WHERE code_insee = {ph_c}", (code,)
                    )
                    id_reg_r = cursor_c.fetchone()
                    cursor_c.execute(
                        f"SELECT id_source FROM {tbl_src} WHERE source_name = {ph_c}", (source,)
                    )
                    id_src_r = cursor_c.fetchone()
                    if not id_reg_r or not id_src_r:
                        continue
                    if is_sqlite_c:
                        cursor_c.execute(
                            f"""INSERT INTO {tbl_cap}
                                    (id_region, id_source, puissance_installee_mw, annee)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(id_region, id_source, annee) DO UPDATE SET
                                    puissance_installee_mw = excluded.puissance_installee_mw""",
                            (id_reg_r[0], id_src_r[0], puissance, annee),
                        )
                    else:
                        cursor_c.execute(
                            f"""INSERT INTO {tbl_cap}
                                    (id_region, id_source, puissance_installee_mw, annee)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (id_region, id_source, annee) DO UPDATE SET
                                    puissance_installee_mw = EXCLUDED.puissance_installee_mw""",
                            (id_reg_r[0], id_src_r[0], puissance, annee),
                        )
                    rows_loaded_c += 1
                conn_c.commit()
                results["stages"]["capacity"] = {"status": "success", "rows": rows_loaded_c}
                logger.info("[%s] Capacity: %d rows loaded", job_id, rows_loaded_c)
            finally:
                conn_c.close()

    except Exception as exc:
        logger.error("[%s] Capacity stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["capacity"] = {"status": "failure", "error": str(exc)}

    # ── Stage 6: Maintenance (scraper) — non-fatal ─────────────────────────────
    logger.info("[%s] Stage 6: Maintenance ingestion", job_id)
    try:
        from shared.gold.dim_loader import DimLoader as _DimLoader3
        from datetime import datetime as _datetime, timezone as _tz

        maintenance_url = os.environ.get("MAINTENANCE_SCRAPING_URL", "")
        maintenance_events: list[dict] = []

        if maintenance_url:
            try:
                scraper = MaintenanceScraper(base_url=maintenance_url)
                maintenance_events = scraper.scrape_from_url()
            except Exception as scrape_exc:
                logger.warning("[%s] Maintenance scraping failed (non-fatal): %s", job_id, scrape_exc)

        if not maintenance_events:
            results["stages"]["maintenance"] = {"status": "empty", "rows": 0}
        else:
            conn_mn = _get_db_connection()
            try:
                dim_mn = _DimLoader3(conn_mn)
                dim_mn.ensure_schema()

                import sqlite3 as _sqlite3_mn
                is_sqlite_mn = isinstance(conn_mn, _sqlite3_mn.Connection)
                tbl_mnt = "FACT_MAINTENANCE" if is_sqlite_mn else "fact_maintenance"
                now_str = _datetime.now(_tz.utc).isoformat()

                cursor_mn = conn_mn.cursor()
                rows_loaded_mn = 0
                for evt in maintenance_events:
                    event_id = evt.get("event_id", "").strip()
                    if not event_id:
                        continue
                    if is_sqlite_mn:
                        cursor_mn.execute(
                            f"""INSERT INTO {tbl_mnt}
                                    (event_id, unit_name, event_type,
                                     start_date, end_date, unavailable_mw, scraped_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(event_id) DO UPDATE SET
                                    unit_name      = excluded.unit_name,
                                    event_type     = excluded.event_type,
                                    start_date     = excluded.start_date,
                                    end_date       = excluded.end_date,
                                    unavailable_mw = excluded.unavailable_mw,
                                    scraped_at     = excluded.scraped_at""",
                            (
                                event_id,
                                evt.get("unit_name"),
                                evt.get("event_type"),
                                evt.get("start_date"),
                                evt.get("end_date"),
                                evt.get("unavailable_mw"),
                                now_str,
                            ),
                        )
                    else:
                        cursor_mn.execute(
                            f"""INSERT INTO {tbl_mnt}
                                    (event_id, unit_name, event_type,
                                     start_date, end_date, unavailable_mw, scraped_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (event_id) DO UPDATE SET
                                    unit_name      = EXCLUDED.unit_name,
                                    event_type     = EXCLUDED.event_type,
                                    start_date     = EXCLUDED.start_date,
                                    end_date       = EXCLUDED.end_date,
                                    unavailable_mw = EXCLUDED.unavailable_mw,
                                    scraped_at     = EXCLUDED.scraped_at""",
                            (
                                event_id,
                                evt.get("unit_name"),
                                evt.get("event_type"),
                                evt.get("start_date"),
                                evt.get("end_date"),
                                evt.get("unavailable_mw"),
                                now_str,
                            ),
                        )
                    rows_loaded_mn += 1
                conn_mn.commit()
                results["stages"]["maintenance"] = {"status": "success", "rows": rows_loaded_mn}
                logger.info("[%s] Maintenance: %d rows loaded", job_id, rows_loaded_mn)
            finally:
                conn_mn.close()

    except Exception as exc:
        logger.error("[%s] Maintenance stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["maintenance"] = {"status": "failure", "error": str(exc)}

    # ── Stage 7: Prix marché (ENTSO-E) — non-fatal ────────────────────────────
    logger.info("[%s] Stage 7: Prix marché ingestion (ENTSO-E)", job_id)
    try:
        from datetime import datetime as _datetime_p, timezone as _tz_p, timedelta as _td_p
        from shared.entsoe_client import EntsoeClient, EntsoeClientError
        from shared.transformations.price_silver import transform_price_to_silver
        from shared.gold.dim_loader import DimLoader as _DimLoader4

        entsoe_token = os.environ.get("ENTSOE_API_TOKEN", "")
        if not entsoe_token:
            results["stages"]["price"] = {"status": "skipped", "reason": "no ENTSOE_API_TOKEN"}
        else:
            now_p = _datetime_p.now(_tz_p.utc)
            # 26h lookback comfortably covers the current market day regardless
            # of DST offset; ON CONFLICT(id_date) DO UPDATE below makes
            # re-fetching overlapping slots on every run harmless.
            period_start_p = now_p - _td_p(hours=26)
            price_client = EntsoeClient(api_token=entsoe_token)
            price_records = price_client.fetch_day_ahead_prices(period_start_p, now_p)
            df_price = transform_price_to_silver(price_records)

            if df_price.empty:
                results["stages"]["price"] = {"status": "empty", "rows": 0}
            else:
                conn_p = _get_db_connection()
                try:
                    dim_p = _DimLoader4(conn_p)
                    dim_p.ensure_schema()
                    timestamps_p = df_price["timestamp"].apply(
                        lambda t: t.strftime("%Y-%m-%dT%H:%M:00")
                    ).tolist()
                    dim_p.upsert_time(timestamps_p)

                    import sqlite3 as _sqlite3_p
                    is_sqlite_p = isinstance(conn_p, _sqlite3_p.Connection)
                    ph_p = "?" if is_sqlite_p else "%s"
                    tbl_pr = "FACT_MARKET_PRICE" if is_sqlite_p else "fact_market_price"
                    tbl_dt_p = "DIM_TIME" if is_sqlite_p else "dim_time"
                    now_str_p = now_p.isoformat()

                    cursor_p = conn_p.cursor()
                    rows_loaded_p = 0
                    for _, row in df_price.iterrows():
                        ts_str_p = row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")
                        cursor_p.execute(
                            f"SELECT id_date FROM {tbl_dt_p} WHERE horodatage = {ph_p}", (ts_str_p,)
                        )
                        id_date_p = cursor_p.fetchone()
                        if not id_date_p:
                            continue
                        if is_sqlite_p:
                            cursor_p.execute(
                                f"""INSERT INTO {tbl_pr} (id_date, price_eur_mwh, retrieved_at)
                                    VALUES (?, ?, ?)
                                    ON CONFLICT(id_date) DO UPDATE SET
                                        price_eur_mwh = excluded.price_eur_mwh,
                                        retrieved_at  = excluded.retrieved_at""",
                                (id_date_p[0], row["price_eur_mwh"], now_str_p),
                            )
                        else:
                            cursor_p.execute(
                                f"""INSERT INTO {tbl_pr} (id_date, price_eur_mwh, retrieved_at)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (id_date) DO UPDATE SET
                                        price_eur_mwh = EXCLUDED.price_eur_mwh,
                                        retrieved_at  = EXCLUDED.retrieved_at""",
                                (id_date_p[0], row["price_eur_mwh"], now_str_p),
                            )
                        rows_loaded_p += 1
                    conn_p.commit()
                    results["stages"]["price"] = {"status": "success", "rows": rows_loaded_p}
                    logger.info("[%s] Prix marché: %d rows loaded", job_id, rows_loaded_p)
                finally:
                    conn_p.close()

    except EntsoeClientError as exc:
        logger.warning("[%s] Prix marché stage failed (non-fatal): %s", job_id, exc)
        results["stages"]["price"] = {"status": "failure", "error": str(exc)}
    except Exception as exc:
        logger.error("[%s] Prix marché stage failed: %s", job_id, exc, exc_info=True)
        results["stages"]["price"] = {"status": "failure", "error": str(exc)}

    return results


# ─── Local dev entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_ingestion(local_mode=True)
    print(f"\nResult: {result['status']} — {result['record_count']} records")
