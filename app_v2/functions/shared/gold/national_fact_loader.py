"""
National Fact Loader — loads RTE's national-only fossil thermal breakdown
(gaz/charbon/fioul) into FACT_NATIONAL_MIX.

Separate from FactLoader/FACT_ENERGY_FLOW because this dimension has no
region: RTE's regional feed never splits fossil thermal by fuel type, only
the national eco2mix dataset does (see national_silver.py).
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from shared.gold.dim_loader import DimLoader

logger = logging.getLogger(__name__)

SOURCE_COLUMN_MAP = {
    "gaz_mw": "gaz",
    "charbon_mw": "charbon",
    "fioul_mw": "fioul",
}


class NationalFactLoader:
    """Load FACT_NATIONAL_MIX from Silver Parquet + DIM references."""

    def __init__(self, db_connection: Any):
        self.conn = db_connection
        self.dim = DimLoader(db_connection)

    def load_from_silver(self, silver_path: str | Path) -> dict:
        silver_path = Path(silver_path)

        if silver_path.is_file():
            df = pd.read_parquet(silver_path)
        elif silver_path.is_dir():
            parquets = sorted(silver_path.rglob("*.parquet"))
            if not parquets:
                return {"status": "empty", "rows_loaded": 0}
            df = pd.concat([pd.read_parquet(f) for f in parquets], ignore_index=True)
        else:
            raise FileNotFoundError(f"Silver path not found: {silver_path}")

        if df.empty:
            return {"status": "empty", "rows_loaded": 0}

        self.dim.ensure_schema()
        self.dim.upsert_sources()

        if "date_heure" in df.columns:
            timestamps = df["date_heure"].astype(str).unique().tolist()
            self.dim.upsert_time(timestamps)

        source_cols = [c for c in SOURCE_COLUMN_MAP if c in df.columns]
        if not source_cols:
            return {"status": "empty", "rows_loaded": 0}

        long_df = (
            df[["date_heure"] + source_cols]
            .melt(id_vars=["date_heure"], value_vars=source_cols,
                  var_name="source_col", value_name="valeur_mw")
            .dropna(subset=["valeur_mw"])
        )
        ts = pd.to_datetime(long_df["date_heure"], utc=True, errors="coerce")
        long_df["horodatage"] = ts.dt.tz_localize(None) if ts.dt.tz is None else ts.dt.tz_convert(None)
        long_df["source_name"] = long_df["source_col"].map(SOURCE_COLUMN_MAP)  # type: ignore[arg-type]
        long_df["valeur_mw"] = pd.to_numeric(long_df["valeur_mw"], errors="coerce")

        cursor = self.conn.cursor()
        rows_loaded = 0

        if self.dim._is_sqlite:
            cursor0 = self.conn.cursor()
            cursor0.execute("SELECT id_date, horodatage FROM DIM_TIME")
            time_map = {}
            for id_date, ts_str in cursor0.fetchall():
                time_map[ts_str] = id_date
            cursor0.execute("SELECT id_source, source_name FROM DIM_SOURCE")
            source_map = {r[1]: r[0] for r in cursor0.fetchall()}
            params = []
            for row in long_df.to_dict("records"):
                id_d = time_map.get(row["horodatage"])
                id_s = source_map.get(row["source_name"])
                if not (id_d and id_s):
                    continue
                params.append((id_d, id_s, row["valeur_mw"]))
            cursor.executemany(
                """INSERT INTO FACT_NATIONAL_MIX (id_date, id_source, valeur_mw)
                   VALUES (?, ?, ?)
                   ON CONFLICT(id_date, id_source) DO UPDATE SET
                       valeur_mw = excluded.valeur_mw""",
                params,
            )
            rows_loaded = len(params)
        else:
            cursor.execute("""
                CREATE TEMP TABLE stg_national (
                    horodatage   TIMESTAMPTZ,
                    source_name  VARCHAR(50),
                    valeur_mw    FLOAT
                )
            """)
            stg_rows = [
                (row["horodatage"], row["source_name"], row["valeur_mw"])
                for row in long_df.to_dict("records")
            ]
            from psycopg2.extras import execute_values
            BATCH = 5000
            for i in range(0, len(stg_rows), BATCH):
                execute_values(cursor, "INSERT INTO stg_national VALUES %s", stg_rows[i:i + BATCH])
                logger.info("Staged %d / %d", min(i + BATCH, len(stg_rows)), len(stg_rows))
            cursor.execute("""
                INSERT INTO fact_national_mix (id_date, id_source, valeur_mw)
                SELECT dt.id_date, ds.id_source, s.valeur_mw
                FROM stg_national s
                JOIN dim_time dt ON dt.horodatage = s.horodatage
                JOIN dim_source ds ON ds.source_name = s.source_name
                ON CONFLICT (id_date, id_source) DO UPDATE SET
                    valeur_mw = EXCLUDED.valeur_mw
            """)
            cursor.execute("DROP TABLE stg_national")
            rows_loaded = len(stg_rows)

        self.conn.commit()

        summary = {
            "status": "success",
            "rows_loaded": rows_loaded,
            "sources": list(SOURCE_COLUMN_MAP.values()),
        }
        logger.info("Gold FACT_NATIONAL_MIX loaded: %d rows", rows_loaded)
        return summary
