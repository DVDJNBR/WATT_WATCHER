"""
Fact Table Loader — Story 3.2, Task 2

Reads Silver Parquet, resolves FK references to DIM tables,
calculates facteur_charge, and INSERTs into FACT_ENERGY_FLOW.
"""

import logging
from datetime import datetime as _dt
from pathlib import Path
from typing import Any

import pandas as pd

from shared.gold.dim_loader import DimLoader

logger = logging.getLogger(__name__)

# Energy sources that map from Silver column names
SOURCE_COLUMN_MAP = {
    "nucleaire_mw": "nucleaire",
    "eolien_mw": "eolien",
    "solaire_mw": "solaire",
    "hydraulique_mw": "hydraulique",
    "gaz_mw": "gaz",
    "charbon_mw": "charbon",
    "fioul_mw": "fioul",
    "bioenergies_mw": "bioenergies",
}


class FactLoader:
    """Load FACT_ENERGY_FLOW from Silver Parquet + DIM references."""

    def __init__(self, db_connection: Any, capacity_data: dict[str, float] | None = None):
        """
        Args:
            db_connection: Database connection.
            capacity_data: Dict mapping source_name → installed capacity (MW)
                          for facteur_charge calculation.
        """
        self.conn = db_connection
        self.dim = DimLoader(db_connection)
        self.capacity = capacity_data or {}

    def load_from_silver(self, silver_path: str | Path) -> dict:
        """
        Read Silver Parquet and load into FACT_ENERGY_FLOW.

        AC #1: Relational join between measurements and asset registry.
        AC #2: Updates FACT with most recent resolved metadata.
        AC #3: DIM tables upserted, FACT rows reference valid dimension keys.

        Args:
            silver_path: Path to Silver Parquet file or directory.

        Returns:
            Summary dict.
        """
        silver_path = Path(silver_path)

        # Read Silver data
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

        # Ensure DIM_SOURCE is populated
        self.dim.upsert_sources()

        # Auto-populate DIM_REGION from Silver data
        if "code_insee_region" in df.columns and "libelle_region" in df.columns:
            regions = (
                df[["code_insee_region", "libelle_region"]]
                .drop_duplicates()
                .to_dict("records")  # type: ignore[call-overload]
            )
            self.dim.upsert_regions([
                {"code_insee": r["code_insee_region"], "nom_region": r["libelle_region"]}
                for r in regions
            ])

        # Auto-populate DIM_TIME from Silver timestamps
        if "date_heure" in df.columns:
            timestamps = df["date_heure"].astype(str).unique().tolist()
            self.dim.upsert_time(timestamps)

        # Unpivot: wide (one row per region/time) → long (one row per region/time/source)
        source_cols = [c for c in SOURCE_COLUMN_MAP if c in df.columns]
        id_cols = [c for c in ["date_heure", "code_insee_region", "temperature_c",
                                "temperature_moyenne"] if c in df.columns]
        long_df = (
            df[id_cols + source_cols]
            .melt(
                id_vars=id_cols,
                value_vars=source_cols,
                var_name="source_col",
                value_name="valeur_mw",
            )
            .dropna(subset=["valeur_mw"])
        )

        # Handle date_heure → horodatage (naive datetime for SQLite lookup)
        ts = pd.to_datetime(long_df["date_heure"], utc=True, errors="coerce")
        long_df["horodatage"] = ts.dt.tz_localize(None) if ts.dt.tz is None else ts.dt.tz_convert(None)
        long_df["source_name"] = long_df["source_col"].map(SOURCE_COLUMN_MAP)  # type: ignore[arg-type]
        long_df["valeur_mw"] = pd.to_numeric(long_df["valeur_mw"], errors="coerce")

        temp_col = "temperature_c" if "temperature_c" in long_df.columns else \
                   ("temperature_moyenne" if "temperature_moyenne" in long_df.columns else None)

        rows_loaded = len(long_df)
        logger.info("Unpivoted to %d long rows", rows_loaded)
        cursor = self.conn.cursor()

        if self.dim._is_sqlite:
            # SQLite: row-by-row with cache
            cursor0 = self.conn.cursor()
            cursor0.execute("SELECT id_region, code_insee FROM DIM_REGION")
            region_map = {r[1]: r[0] for r in cursor0.fetchall()}
            cursor0.execute("SELECT id_date, horodatage FROM DIM_TIME")
            time_map = {}
            for id_date, ts_str in cursor0.fetchall():
                time_map[ts_str] = id_date
                try:
                    ts = _dt.fromisoformat(str(ts_str).replace("Z", "+00:00").replace(" UTC", "+00:00"))
                    time_map[ts.replace(tzinfo=None)] = id_date
                except Exception as e:
                    logger.debug("Could not parse timestamp %r for time_map: %s", ts_str, e)
            cursor0.execute("SELECT id_source, source_name FROM DIM_SOURCE")
            source_map = {r[1]: r[0] for r in cursor0.fetchall()}
            params = []
            for row in long_df.to_dict("records"):
                id_r = region_map.get(str(row["code_insee_region"]))
                id_d = time_map.get(row["horodatage"])
                id_s = source_map.get(row["source_name"])
                if not (id_r and id_d and id_s):
                    continue
                temp = row.get("temperature_c") or row.get("temperature_moyenne")
                facteur = (
                    row["valeur_mw"] / self.capacity[row["source_name"]]
                    if row["source_name"] in self.capacity else None
                )
                params.append((id_d, id_r, id_s, row["valeur_mw"], facteur, temp))
            cursor.executemany(
                """INSERT INTO FACT_ENERGY_FLOW
                   (id_date, id_region, id_source, valeur_mw, facteur_charge, temperature_moyenne)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id_date, id_region, id_source) DO UPDATE SET
                       valeur_mw = excluded.valeur_mw,
                       temperature_moyenne = excluded.temperature_moyenne""",
                params,
            )
            rows_loaded = len(params)
        else:
            # Azure SQL: staging table + JOIN-based MERGE (no Python FK resolution)
            cursor.execute("""
                CREATE TABLE #stg (
                    horodatage      DATETIME2,
                    code_insee      NVARCHAR(10),
                    source_name     NVARCHAR(50),
                    valeur_mw       FLOAT,
                    temperature_moy FLOAT
                )
            """)
            cursor.fast_executemany = True
            stg_rows = [
                (
                    row["horodatage"],
                    str(row["code_insee_region"]),
                    row["source_name"],
                    row["valeur_mw"],
                    row.get(temp_col) if temp_col else None,
                )
                for row in long_df.to_dict("records")
            ]
            BATCH = 5000
            for i in range(0, len(stg_rows), BATCH):
                cursor.executemany("INSERT INTO #stg VALUES (?,?,?,?,?)", stg_rows[i:i+BATCH])
                logger.info("Staged %d / %d", min(i+BATCH, len(stg_rows)), len(stg_rows))
            cursor.execute("""
                MERGE FACT_ENERGY_FLOW AS t
                USING (
                    SELECT dt.id_date, dr.id_region, ds.id_source,
                           s.valeur_mw, s.temperature_moy
                    FROM #stg s
                    JOIN DIM_TIME   dt ON dt.horodatage  = s.horodatage
                    JOIN DIM_REGION dr ON dr.code_insee  = s.code_insee
                    JOIN DIM_SOURCE ds ON ds.source_name = s.source_name
                ) AS src
                ON t.id_date=src.id_date AND t.id_region=src.id_region AND t.id_source=src.id_source
                WHEN MATCHED THEN UPDATE SET
                    valeur_mw=src.valeur_mw, temperature_moyenne=src.temperature_moy
                WHEN NOT MATCHED THEN INSERT
                    (id_date,id_region,id_source,valeur_mw,facteur_charge,temperature_moyenne)
                VALUES (src.id_date,src.id_region,src.id_source,src.valeur_mw,NULL,src.temperature_moy);
            """)
            cursor.execute("DROP TABLE #stg")

        self.conn.commit()

        summary = {
            "status": "success",
            "rows_loaded": rows_loaded,
            "sources": list(SOURCE_COLUMN_MAP.values()),
        }
        logger.info("Gold FACT loaded: %d rows", rows_loaded)
        return summary

    def get_fact_count(self) -> int:
        """Get total rows in FACT_ENERGY_FLOW."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM FACT_ENERGY_FLOW")
        return cursor.fetchone()[0]

    def get_fact_summary(self) -> dict:
        """Get summary stats from FACT_ENERGY_FLOW."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT id_region) as regions,
                COUNT(DISTINCT id_source) as sources,
                COUNT(DISTINCT id_date) as time_slots,
                ROUND(AVG(valeur_mw), 2) as avg_mw,
                SUM(CASE WHEN facteur_charge IS NOT NULL THEN 1 ELSE 0 END) as with_load_factor
            FROM FACT_ENERGY_FLOW
        """)
        row = cursor.fetchone()
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
