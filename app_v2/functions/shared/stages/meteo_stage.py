"""Open-Meteo stage — part of the 15-minute pipeline (weather changes continuously)."""

import logging
import sqlite3
from typing import Any

from shared.db import get_db_connection

logger = logging.getLogger(__name__)

# ~3 months + buffer. Not an exact cutoff: this runs every 15 min alongside
# ingestion (no separate timer), so a few 15-min batches drifting past the
# exact boundary between runs is expected and fine.
RETENTION_DAYS = 95


def run(job_id: str, bronze: Any, silver: Any) -> dict:
    """Fetch Open-Meteo data for every region, Bronze -> Silver -> Gold (fact_meteo)."""
    from shared.open_meteo_client import fetch_meteo_all_regions

    logger.info("[%s] Meteo: ingestion", job_id)
    meteo_records = fetch_meteo_all_regions(past_days=3)
    result = load_meteo_records(job_id, bronze, silver, meteo_records)

    try:
        purged = _purge_old_meteo(job_id)
        result["purged"] = purged
    except Exception as purge_exc:
        logger.warning("[%s] Meteo purge failed (non-fatal): %s", job_id, purge_exc)

    # meteo_grid (current 22x16 canvas-map snapshot) only makes sense for the
    # live forecast run, not a historical backfill — kept out of
    # load_meteo_records so backfill_meteo_history.py doesn't touch it.
    if result.get("status") == "success":
        from shared.db import get_db_connection
        import sqlite3 as _sqlite3

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            is_sqlite = isinstance(conn, _sqlite3.Connection)
            grid_loaded = 0
            try:
                from shared.open_meteo_client import fetch_meteo_grid
                grid_rows = fetch_meteo_grid()
                tbl_grid = "METEO_GRID" if is_sqlite else "meteo_grid"
                for gr in grid_rows:
                    if is_sqlite:
                        cursor.execute(
                            f"""INSERT INTO {tbl_grid} (lat, lon, cloud_cover, wind_speed, wind_direction, updated_at)
                                VALUES (?, ?, ?, ?, ?, datetime('now'))
                                ON CONFLICT(lat, lon) DO UPDATE SET
                                    cloud_cover    = excluded.cloud_cover,
                                    wind_speed     = excluded.wind_speed,
                                    wind_direction = excluded.wind_direction,
                                    updated_at     = excluded.updated_at""",
                            (gr["lat"], gr["lon"], gr["cloud_cover"], gr["wind_speed"], gr["wind_direction"]),
                        )
                    else:
                        cursor.execute(
                            f"""INSERT INTO {tbl_grid} (lat, lon, cloud_cover, wind_speed, wind_direction, updated_at)
                                VALUES (%s, %s, %s, %s, %s, now())
                                ON CONFLICT (lat, lon) DO UPDATE SET
                                    cloud_cover    = EXCLUDED.cloud_cover,
                                    wind_speed     = EXCLUDED.wind_speed,
                                    wind_direction = EXCLUDED.wind_direction,
                                    updated_at     = now()""",
                            (gr["lat"], gr["lon"], gr["cloud_cover"], gr["wind_speed"], gr["wind_direction"]),
                        )
                    grid_loaded += 1
                conn.commit()
                logger.info("[%s] meteo_grid: %d points upserted", job_id, grid_loaded)
                result["grid_points"] = grid_loaded
            except Exception as grid_exc:
                logger.warning("[%s] meteo_grid upsert failed (non-fatal): %s", job_id, grid_exc)
        finally:
            conn.close()

    return result


def _purge_old_meteo(job_id: str) -> int:
    """Delete fact_meteo rows older than RETENTION_DAYS. Doesn't touch
    dim_time — that dimension is shared across every fact table."""
    from datetime import datetime, timedelta, timezone

    conn = get_db_connection()
    try:
        is_sqlite = isinstance(conn, sqlite3.Connection)
        ph = "?" if is_sqlite else "%s"
        tbl_meteo = "FACT_METEO" if is_sqlite else "fact_meteo"
        tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:00")

        cursor = conn.cursor()
        cursor.execute(
            f"""DELETE FROM {tbl_meteo} WHERE id_date IN (
                    SELECT id_date FROM {tbl_time} WHERE horodatage < {ph}
                )""",
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
        if deleted:
            logger.info("[%s] Meteo: purged %d rows older than %d days", job_id, deleted, RETENTION_DAYS)
        return deleted
    finally:
        conn.close()


def load_meteo_records(job_id: str, bronze: Any, silver: Any, meteo_records: list[dict]) -> dict:
    """Bronze -> Silver -> Gold (fact_meteo) for already-fetched météo records.

    Shared by the live 15-minute run() above and scripts/backfill_meteo_history.py
    (which fetches historical records via the Archive API instead of the
    forecast API) — same Gold load either way, no separate write logic to
    keep in sync.
    """
    from shared.transformations.meteo_silver import transform_meteo_to_silver
    from shared.gold.dim_loader import DimLoader
    from shared.open_meteo_client import REGION_CENTROIDS

    try:
        if meteo_records:
            bronze.write_json(meteo_records, source="meteo", sub_path="regional")
        df_meteo = transform_meteo_to_silver(meteo_records)

        if df_meteo.empty:
            return {"status": "empty", "rows": 0}

        df_meteo_part = df_meteo.copy()
        df_meteo_part["year"] = df_meteo_part["timestamp"].dt.year
        df_meteo_part["month"] = df_meteo_part["timestamp"].dt.month
        silver.write_parquet(
            df_meteo_part, source="meteo", sub_path="regional",
            partition_cols=["year", "month"],
        )

        conn = get_db_connection()
        try:
            dim = DimLoader(conn)
            dim.ensure_schema()
            dim.upsert_regions([
                {"code_insee": code, "nom_region": info["name"]}
                for code, info in REGION_CENTROIDS.items()
            ])
            timestamps = df_meteo["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:00").tolist()
            dim.upsert_time(timestamps)

            is_sqlite = isinstance(conn, sqlite3.Connection)
            tbl_meteo = "FACT_METEO" if is_sqlite else "fact_meteo"
            tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
            tbl_region = "DIM_REGION" if is_sqlite else "dim_region"

            cursor = conn.cursor()

            # Bulk-fetch id_date/id_region lookups once instead of 2 SELECTs
            # per row — a 90-day backfill is ~28k rows, and row-by-row against
            # a remote Postgres (Supabase) turns into ~85k network round
            # trips, which in practice never finishes in reasonable time.
            unique_ts = sorted(set(df_meteo["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:00")))
            if is_sqlite:
                placeholders = ",".join("?" * len(unique_ts))
                cursor.execute(
                    f"SELECT id_date, horodatage FROM {tbl_time} WHERE horodatage IN ({placeholders})",
                    unique_ts,
                )
            else:
                cursor.execute(
                    f"SELECT id_date, horodatage FROM {tbl_time} WHERE horodatage = ANY(%s::timestamptz[])",
                    (unique_ts,),
                )
            fetched = cursor.fetchall()
            if is_sqlite:
                date_map = {horodatage: id_date for id_date, horodatage in fetched}
            else:
                # psycopg2 returns horodatage as a tz-aware datetime, not the
                # original string — reformat to the same key shape as ts_str.
                date_map = {
                    horodatage.strftime("%Y-%m-%dT%H:%M:00"): id_date
                    for id_date, horodatage in fetched
                }

            cursor.execute(f"SELECT id_region, code_insee FROM {tbl_region}")
            region_map = {code_insee: id_region for id_region, code_insee in cursor.fetchall()}

            insert_rows = []
            for _, row in df_meteo.iterrows():
                ts_str = row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")
                id_date = date_map.get(ts_str)
                id_region = region_map.get(row["region_code"])
                if id_date is None or id_region is None:
                    continue
                cloud = row.get("cloudcover_pct")
                cloud = float(cloud) if cloud is not None and cloud == cloud else None
                insert_rows.append((id_date, id_region, row["temperature_c"], row.get("wind_speed_10m"), cloud))

            rows_loaded = 0
            if insert_rows:
                if is_sqlite:
                    cursor.executemany(
                        f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id_date, id_region) DO UPDATE SET
                                temperature_c  = excluded.temperature_c,
                                wind_speed_10m = excluded.wind_speed_10m,
                                cloudcover_pct = excluded.cloudcover_pct""",
                        insert_rows,
                    )
                else:
                    from psycopg2.extras import execute_values
                    execute_values(
                        cursor,
                        f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                            VALUES %s
                            ON CONFLICT (id_date, id_region) DO UPDATE SET
                                temperature_c  = EXCLUDED.temperature_c,
                                wind_speed_10m = EXCLUDED.wind_speed_10m,
                                cloudcover_pct = EXCLUDED.cloudcover_pct""",
                        insert_rows,
                    )
                rows_loaded = len(insert_rows)
            conn.commit()
            logger.info("[%s] Meteo: %d rows loaded", job_id, rows_loaded)

            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except Exception as exc:
        logger.error("[%s] Meteo stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
