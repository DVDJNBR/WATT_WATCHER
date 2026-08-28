"""ODRE installed-capacity stage — part of the weekly pipeline.

The national capacity registry is updated ~once a year (see
odre_capacity_client.py); checking every 15 minutes was pure waste
(the original bug this restructuring fixes). Weekly is a comfortable
margin, not a hard requirement.
"""

import logging
import sqlite3
from typing import Any

from shared.db import get_db_connection

logger = logging.getLogger(__name__)


def run(job_id: str, bronze: Any, silver: Any) -> dict:
    """Fetch ODRE's capacity registry, Bronze (raw CSV) -> Silver -> Gold (fact_capacity)."""
    from shared.odre_capacity_client import fetch_raw_csv, parse_capacity_csv
    from shared.transformations.capacity_silver import records_to_silver_df
    from shared.gold.dim_loader import DimLoader

    logger.info("[%s] Capacity: ingestion (ODRE)", job_id)
    try:
        capacity_csv = fetch_raw_csv()
        bronze.write_text(capacity_csv, source="capacity", extension="csv")
        capacity_records = parse_capacity_csv(capacity_csv)

        if not capacity_records:
            return {"status": "empty", "rows": 0}

        df_capacity = records_to_silver_df(capacity_records)
        silver.write_parquet(df_capacity, source="capacity")

        conn = get_db_connection()
        try:
            dim = DimLoader(conn)
            dim.ensure_schema()
            dim.upsert_sources()

            regions = {}
            for rec in capacity_records:
                code = rec.get("region_code")
                name = rec.get("region_name")
                if code and name and code not in regions:
                    regions[code] = name
            if regions:
                dim.upsert_regions([
                    {"code_insee": code, "nom_region": name}
                    for code, name in regions.items()
                ])

            is_sqlite = isinstance(conn, sqlite3.Connection)
            ph = "?" if is_sqlite else "%s"
            tbl_capacity = "FACT_CAPACITY" if is_sqlite else "fact_capacity"
            tbl_region = "DIM_REGION" if is_sqlite else "dim_region"
            tbl_source = "DIM_SOURCE" if is_sqlite else "dim_source"

            cursor = conn.cursor()
            rows_loaded = 0
            for rec in capacity_records:
                code = rec.get("region_code")
                source = rec.get("source_name")
                puissance = rec.get("puissance_installee_mw")
                annee = rec.get("annee")
                if not code or not source:
                    continue
                cursor.execute(f"SELECT id_region FROM {tbl_region} WHERE code_insee = {ph}", (code,))
                id_reg_r = cursor.fetchone()
                cursor.execute(f"SELECT id_source FROM {tbl_source} WHERE source_name = {ph}", (source,))
                id_src_r = cursor.fetchone()
                if not id_reg_r or not id_src_r:
                    continue
                if is_sqlite:
                    cursor.execute(
                        f"""INSERT INTO {tbl_capacity}
                                (id_region, id_source, puissance_installee_mw, annee)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(id_region, id_source, annee) DO UPDATE SET
                                puissance_installee_mw = excluded.puissance_installee_mw""",
                        (id_reg_r[0], id_src_r[0], puissance, annee),
                    )
                else:
                    cursor.execute(
                        f"""INSERT INTO {tbl_capacity}
                                (id_region, id_source, puissance_installee_mw, annee)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (id_region, id_source, annee) DO UPDATE SET
                                puissance_installee_mw = EXCLUDED.puissance_installee_mw""",
                        (id_reg_r[0], id_src_r[0], puissance, annee),
                    )
                rows_loaded += 1
            conn.commit()
            logger.info("[%s] Capacity: %d rows loaded", job_id, rows_loaded)
            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except Exception as exc:
        logger.error("[%s] Capacity stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
