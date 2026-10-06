"""
Météo Fact Loader — loads Silver-normalized Open-Meteo regional data into
FACT_METEO, resolving its DIM_TIME / DIM_REGION references.

Shared by the admin pipeline (run_full_pipeline) and the 15-minute
meteo_regional_refresh timer, so both paths write Gold the same way.
"""

import logging
import sqlite3
from typing import Any

import pandas as pd

from shared.gold.dim_loader import DimLoader
from shared.open_meteo_client import REGION_CENTROIDS

logger = logging.getLogger(__name__)


def load_meteo_to_gold(df_meteo: pd.DataFrame, conn: Any) -> int:
    """
    Upsert DIM_REGION / DIM_TIME, then load FACT_METEO from a Silver
    DataFrame (columns: region_code, timestamp, temperature_c,
    wind_speed_10m, cloudcover_pct).

    Returns the number of FACT_METEO rows loaded (0 if df_meteo is empty).
    """
    if df_meteo.empty:
        return 0

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
        id_date = cursor.fetchone()
        cursor.execute(
            f"SELECT id_region FROM {tbl_region} WHERE code_insee = {ph}", (row["region_code"],)
        )
        id_region = cursor.fetchone()
        if not id_date or not id_region:
            continue

        cloud = row.get("cloudcover_pct")
        cloud = float(cloud) if cloud is not None and cloud == cloud else None
        params = (id_date[0], id_region[0], row["temperature_c"], row.get("wind_speed_10m"), cloud)

        if is_sqlite:
            cursor.execute(
                f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id_date, id_region) DO UPDATE SET
                        temperature_c  = excluded.temperature_c,
                        wind_speed_10m = excluded.wind_speed_10m,
                        cloudcover_pct = excluded.cloudcover_pct""",
                params,
            )
        else:
            cursor.execute(
                f"""INSERT INTO {tbl_meteo} (id_date, id_region, temperature_c, wind_speed_10m, cloudcover_pct)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id_date, id_region) DO UPDATE SET
                        temperature_c  = EXCLUDED.temperature_c,
                        wind_speed_10m = EXCLUDED.wind_speed_10m,
                        cloudcover_pct = EXCLUDED.cloudcover_pct""",
                params,
            )
        rows_loaded += 1
        if rows_loaded % 500 == 0:
            conn.commit()

    conn.commit()
    logger.info("Météo Gold: %d rows loaded into FACT_METEO", rows_loaded)
    return rows_loaded
