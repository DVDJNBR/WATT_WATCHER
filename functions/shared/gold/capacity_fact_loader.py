"""
Capacity Fact Loader — loads Silver-normalized ODRE installed-capacity data
into FACT_CAPACITY, resolving its DIM_REGION / DIM_SOURCE references.

Reads Silver Parquet rather than re-fetching ODRE, mirroring
FactLoader.load_from_silver: Gold should be built from what Silver actually
wrote, not from a second live call that could disagree with it.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from shared.gold.dim_loader import DimLoader
from shared.odre_capacity_client import FILIERE_MAP

logger = logging.getLogger(__name__)


def load_capacity_to_gold(silver_path: str | Path, conn: Any) -> int:
    """
    Read Silver Parquet (file or directory) and upsert FACT_CAPACITY.

    Returns the number of rows loaded (0 if the Silver path is empty).
    """
    silver_path = Path(silver_path)

    if silver_path.is_file():
        df = pd.read_parquet(silver_path)
    elif silver_path.is_dir():
        parquets = sorted(silver_path.rglob("*.parquet"))
        if not parquets:
            return 0
        df = pd.concat([pd.read_parquet(f) for f in parquets], ignore_index=True)
    else:
        raise FileNotFoundError(f"Silver path not found: {silver_path}")

    if df.empty:
        return 0

    dim = DimLoader(conn)
    dim.ensure_schema()
    dim.upsert_sources()

    # ODRE's CSV gives `code_insee_region` as a bare number, so pandas reads
    # the whole column as float64 ("53.0") — every other source's Silver
    # output carries it as a plain string ("53"). Left as a float, DIM_REGION
    # picks up a new row each run instead of matching the one already there:
    # no conflict fires, FACT_CAPACITY just grows. Normalized once, here, at
    # the SQL boundary — found by re-running this against the real API twice
    # in a row and watching the row count double instead of hold steady.
    def _code(v):
        return str(int(v)) if pd.notna(v) else None

    if "code_insee_region" in df.columns and "libelle_region" in df.columns:
        regions = df[["code_insee_region", "libelle_region"]].drop_duplicates().to_dict("records")
        dim.upsert_regions([
            {"code_insee": _code(r["code_insee_region"]), "nom_region": r["libelle_region"]}
            for r in regions if _code(r["code_insee_region"])
        ])

    is_sqlite = isinstance(conn, sqlite3.Connection)
    ph = "?" if is_sqlite else "%s"
    tbl_cap = "FACT_CAPACITY" if is_sqlite else "fact_capacity"
    tbl_reg = "DIM_REGION" if is_sqlite else "dim_region"
    tbl_src = "DIM_SOURCE" if is_sqlite else "dim_source"

    cursor = conn.cursor()
    rows_loaded = 0
    for _, row in df.iterrows():
        code = _code(row.get("code_insee_region"))
        filiere_raw = str(row.get("filiere", "")).strip().lower()
        source_name = FILIERE_MAP.get(filiere_raw)
        if not code or not source_name:
            continue

        cursor.execute(f"SELECT id_region FROM {tbl_reg} WHERE code_insee = {ph}", (code,))
        id_region = cursor.fetchone()
        cursor.execute(f"SELECT id_source FROM {tbl_src} WHERE source_name = {ph}", (source_name,))
        id_source = cursor.fetchone()
        if not id_region or not id_source:
            continue

        # ODRE's regional-aggregate export carries no year column (see
        # odre_capacity_client.py's select clause), so annee stays NULL. SQL
        # treats NULL as never equal to NULL, even inside a UNIQUE constraint
        # — UNIQUE(id_region, id_source, annee) therefore never recognizes
        # two NULL-annee rows for the same region/source as the same row, and
        # ON CONFLICT silently never fires: every re-run just inserts fresh
        # duplicates instead of updating. Found by running this against the
        # real API twice in a row and watching the count double. With no
        # ON CONFLICT to lean on, the NULL-annee case clears its own slot by
        # hand first — delete then insert — which is the direct fix and
        # doesn't require fabricating a fake year to make the constraint work.
        puissance = row.get("puissance_installee_mw")

        if is_sqlite:
            cursor.execute(
                f"""DELETE FROM {tbl_cap}
                    WHERE id_region = {ph} AND id_source = {ph} AND annee IS NULL""",
                (id_region[0], id_source[0]),
            )
            cursor.execute(
                f"""INSERT INTO {tbl_cap} (id_region, id_source, puissance_installee_mw, annee)
                    VALUES (?, ?, ?, NULL)""",
                (id_region[0], id_source[0], puissance),
            )
        else:
            cursor.execute(
                f"""DELETE FROM {tbl_cap}
                    WHERE id_region = {ph} AND id_source = {ph} AND annee IS NULL""",
                (id_region[0], id_source[0]),
            )
            cursor.execute(
                f"""INSERT INTO {tbl_cap} (id_region, id_source, puissance_installee_mw, annee)
                    VALUES (%s, %s, %s, NULL)""",
                (id_region[0], id_source[0], puissance),
            )
        rows_loaded += 1
        if rows_loaded % 500 == 0:
            conn.commit()

    conn.commit()
    logger.info("Capacity Gold: %d rows loaded into FACT_CAPACITY", rows_loaded)
    return rows_loaded
