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

# Raw ODRE CSV names → the canonical names this module's own quality rules
# and dedup already expect (`code_insee_region`, `puissance_installee_mw`).
# Without this, `CAPACITY_QUALITY_RULES` and `dedup_cols` below silently
# no-op — `apply_quality_rules` and the dedup both guard on `col in
# df.columns`, so a name mismatch fails open, not loud. This module ran for
# the first time end-to-end only once capacity got a real Bronze/Silver/Gold
# path instead of a Gold-only shortcut inside the manual admin pipeline, and
# that first real run is what surfaced the mismatch.
RENAME_MAP = {
    "coderegion": "code_insee_region",
    "region": "libelle_region",
    "puismaxinstallee": "puissance_installee_mw",
}


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

    # Normalize column names → snake_case, then map ODRE's raw names to the
    # canonical ones the rest of this function expects.
    df.columns = [c.lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    df = df.rename(columns=RENAME_MAP)

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
