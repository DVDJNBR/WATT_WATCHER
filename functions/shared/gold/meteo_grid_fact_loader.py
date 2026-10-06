"""
Météo Grid Fact Loader — loads the 352-point Open-Meteo grid into
FACT_METEO_GRID, with its own DIM_GRID_POINT dimension keyed by (lat, lon)
rather than INSEE region: the grid is a spatial raster for the live map,
not an administrative entity, so it doesn't belong in DIM_REGION.

No DIM_TIME join either. FACT_METEO_GRID is 1:1 with DIM_GRID_POINT and
upserted in place on every cycle — the same "always now, no history"
semantic the Supabase meteo_grid cache already had, just inside the
official Gold schema instead of a side table reached only via PostgREST.
"""

import logging
import sqlite3
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def ensure_grid_schema(conn: Any) -> None:
    """Create DIM_GRID_POINT / FACT_METEO_GRID if they don't exist yet."""
    is_sqlite = isinstance(conn, sqlite3.Connection)
    cursor = conn.cursor()

    if is_sqlite:
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS DIM_GRID_POINT (
                id_point INTEGER PRIMARY KEY AUTOINCREMENT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                UNIQUE(lat, lon)
            );

            CREATE TABLE IF NOT EXISTS FACT_METEO_GRID (
                id_point INTEGER PRIMARY KEY REFERENCES DIM_GRID_POINT(id_point),
                cloud_cover REAL,
                wind_speed_10m REAL,
                wind_direction_10m REAL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
    else:
        statements = [
            """CREATE TABLE IF NOT EXISTS dim_grid_point (
                   id_point  SERIAL         PRIMARY KEY,
                   lat       NUMERIC(5,2)   NOT NULL,
                   lon       NUMERIC(5,2)   NOT NULL,
                   UNIQUE (lat, lon)
               )""",
            """CREATE TABLE IF NOT EXISTS fact_meteo_grid (
                   id_point            INT            PRIMARY KEY REFERENCES dim_grid_point(id_point),
                   cloud_cover         NUMERIC(5,2),
                   wind_speed_10m      NUMERIC(6,2),
                   wind_direction_10m  NUMERIC(6,2),
                   updated_at          TIMESTAMPTZ    NOT NULL DEFAULT NOW()
               )""",
        ]
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()

    logger.info("Grid Gold schema ensured (%s)", "SQLite" if is_sqlite else "Postgres")


def load_grid_to_gold(df: pd.DataFrame, conn: Any) -> int:
    """Upsert DIM_GRID_POINT, then upsert FACT_METEO_GRID in place (no history)."""
    if df.empty:
        return 0

    ensure_grid_schema(conn)
    is_sqlite = isinstance(conn, sqlite3.Connection)
    ph = "?" if is_sqlite else "%s"
    tbl_point = "DIM_GRID_POINT" if is_sqlite else "dim_grid_point"
    tbl_fact = "FACT_METEO_GRID" if is_sqlite else "fact_meteo_grid"

    cursor = conn.cursor()
    rows_loaded = 0

    for _, row in df.iterrows():
        lat, lon = float(row["lat"]), float(row["lon"])

        cursor.execute(
            f"INSERT INTO {tbl_point} (lat, lon) VALUES ({ph}, {ph}) "
            f"ON CONFLICT (lat, lon) DO NOTHING",
            (lat, lon),
        )
        cursor.execute(f"SELECT id_point FROM {tbl_point} WHERE lat = {ph} AND lon = {ph}", (lat, lon))
        id_point = cursor.fetchone()[0]

        params = (id_point, row.get("cloud_cover"), row.get("wind_speed"), row.get("wind_direction"))
        if is_sqlite:
            cursor.execute(
                f"""INSERT INTO {tbl_fact} (id_point, cloud_cover, wind_speed_10m, wind_direction_10m, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id_point) DO UPDATE SET
                        cloud_cover        = excluded.cloud_cover,
                        wind_speed_10m     = excluded.wind_speed_10m,
                        wind_direction_10m = excluded.wind_direction_10m,
                        updated_at         = excluded.updated_at""",
                params,
            )
        else:
            cursor.execute(
                f"""INSERT INTO {tbl_fact} (id_point, cloud_cover, wind_speed_10m, wind_direction_10m, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (id_point) DO UPDATE SET
                        cloud_cover        = EXCLUDED.cloud_cover,
                        wind_speed_10m     = EXCLUDED.wind_speed_10m,
                        wind_direction_10m = EXCLUDED.wind_direction_10m,
                        updated_at         = EXCLUDED.updated_at""",
                params,
            )
        rows_loaded += 1
        if rows_loaded % 500 == 0:
            conn.commit()

    conn.commit()
    logger.info("Météo Grid Gold: %d rows upserted into FACT_METEO_GRID", rows_loaded)
    return rows_loaded
