"""Open-Meteo stage — part of the 15-minute pipeline (weather changes continuously)."""

import logging
import sqlite3
from typing import Any

from shared.db import get_db_connection

logger = logging.getLogger(__name__)


def run(job_id: str, bronze: Any, silver: Any) -> dict:
    """Fetch Open-Meteo data for every region, Bronze -> Silver -> Gold (fact_meteo)."""
    from shared.open_meteo_client import fetch_meteo_all_regions, REGION_CENTROIDS
    from shared.transformations.meteo_silver import transform_meteo_to_silver
    from shared.gold.dim_loader import DimLoader

    logger.info("[%s] Meteo: ingestion", job_id)
    try:
        meteo_records = fetch_meteo_all_regions(past_days=3)
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
            ph = "?" if is_sqlite else "%s"
            tbl_meteo = "FACT_METEO" if is_sqlite else "fact_meteo"
            tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
            tbl_region = "DIM_REGION" if is_sqlite else "dim_region"

            cursor = conn.cursor()
            rows_loaded = 0
            for _, row in df_meteo.iterrows():
                ts_str = row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")
                cursor.execute(f"SELECT id_date FROM {tbl_time} WHERE horodatage = {ph}", (ts_str,))
                id_date_r = cursor.fetchone()
                cursor.execute(f"SELECT id_region FROM {tbl_region} WHERE code_insee = {ph}", (row["region_code"],))
                id_region_r = cursor.fetchone()
                if not id_date_r or not id_region_r:
                    continue
                cloud = row.get("cloudcover_pct")
                cloud = float(cloud) if cloud is not None and cloud == cloud else None
                if is_sqlite:
                    cursor.execute(
                        f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id_date, id_region) DO UPDATE SET
                                temperature_c  = excluded.temperature_c,
                                wind_speed_10m = excluded.wind_speed_10m,
                                cloudcover_pct = excluded.cloudcover_pct""",
                        (id_date_r[0], id_region_r[0], row["temperature_c"], row.get("wind_speed_10m"), cloud),
                    )
                else:
                    cursor.execute(
                        f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (id_date, id_region) DO UPDATE SET
                                temperature_c  = EXCLUDED.temperature_c,
                                wind_speed_10m = EXCLUDED.wind_speed_10m,
                                cloudcover_pct = EXCLUDED.cloudcover_pct""",
                        (id_date_r[0], id_region_r[0], row["temperature_c"], row.get("wind_speed_10m"), cloud),
                    )
                rows_loaded += 1
                if rows_loaded % 500 == 0:
                    conn.commit()
            conn.commit()
            logger.info("[%s] Meteo: %d rows loaded", job_id, rows_loaded)
            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except Exception as exc:
        logger.error("[%s] Meteo stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
