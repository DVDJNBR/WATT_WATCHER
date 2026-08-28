"""
Capacity Silver Transformation — Story 3.1, Task 2

Cleans Bronze CSV capacity data:
- Snake_case column normalization
- Handle missing values (FILL_ZERO for puissance)
- Output Hive-partitioned Parquet
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from shared.transformations.data_quality import (
    CAPACITY_QUALITY_RULES,
    apply_quality_rules,
)

logger = logging.getLogger(__name__)


def records_to_silver_df(records: list[dict]) -> pd.DataFrame:
    """
    Build the Silver DataFrame for the live ODRE capacity path.

    `odre_capacity_client.fetch_capacity()` already parses, converts units
    (kW → MW), aggregates by (region, source) and drops zero/invalid rows —
    the records it returns are already clean. This just gives that already-clean
    data a typed DataFrame shape for Silver persistence, without duplicating
    `_parse_capacity_csv`'s column-detection logic (which targets ODRE's raw
    export columns, not the legacy/differently-shaped schema `transform_capacity_to_silver`
    below was built for).
    """
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "puissance_installee_mw" in df.columns:
        df["puissance_installee_mw"] = pd.to_numeric(df["puissance_installee_mw"], errors="coerce")
    if "annee" in df.columns:
        df["annee"] = pd.to_numeric(df["annee"], errors="coerce").astype("Int64")
    return df


def transform_capacity_to_silver(
    bronze_path: str | Path,
    output_dir: str | Path,
) -> dict:
    """Transform capacity Bronze CSV → Silver Parquet."""
    bronze_path = Path(bronze_path)
    output_dir = Path(output_dir)

    if bronze_path.is_file():
        df = pd.read_csv(bronze_path, sep=";")
    elif bronze_path.is_dir():
        csvs = sorted(bronze_path.rglob("*.csv"))
        if not csvs:
            return {"status": "empty", "rows": 0}
        df = pd.concat([pd.read_csv(f, sep=";") for f in csvs], ignore_index=True)
    else:
        raise FileNotFoundError(f"Bronze path not found: {bronze_path}")

    # Normalize column names → snake_case
    df.columns = [c.lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    # Cast numeric columns
    if "puissance_installee_mw" in df.columns:
        df["puissance_installee_mw"] = pd.to_numeric(
            df["puissance_installee_mw"], errors="coerce"
        )

    # Apply quality rules
    df, quality = apply_quality_rules(df, CAPACITY_QUALITY_RULES, "capacity")

    # Deduplicate
    before = len(df)
    dedup_cols = [c for c in ["code_insee_region", "filiere"] if c in df.columns]
    if dedup_cols:
        df = df.drop_duplicates(subset=dedup_cols, keep="last")

    # Write to Silver
    out_path = output_dir / "silver/reference/capacity/data.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    summary = {
        "status": "success",
        "input_rows": before,
        "output_rows": len(df),
        "files_written": 1,
        "quality": quality,
    }
    logger.info("Capacity Silver: %d → %d rows", before, len(df))
    return summary
