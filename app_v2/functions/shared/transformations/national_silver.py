"""
National Silver Transformation — RTE's eco2mix-national-tr dataset, the
only one that splits fossil thermal by fuel type (gaz/charbon/fioul). The
regional feed (rte_silver.py) only ever carries one combined "thermique"
figure, so this is a separate, smaller pipeline: no region dimension,
France-wide only.
"""

import logging
from pathlib import Path

import pandas as pd

from shared.transformations.data_quality import RTE_QUALITY_RULES, apply_quality_rules
from shared.transformations.rte_silver import _load_json_file, _write_hive_partitioned

logger = logging.getLogger(__name__)

MW_CAST_COLUMNS = ["gaz", "charbon", "fioul"]
RENAME_MAP = {"gaz": "gaz_mw", "charbon": "charbon_mw", "fioul": "fioul_mw"}


def transform_national_to_silver(
    bronze_path: str | Path,
    output_dir: str | Path,
) -> dict:
    """Transform national eco2mix Bronze JSON -> Silver Parquet."""
    bronze_path = Path(bronze_path)
    output_dir = Path(output_dir)

    if bronze_path.is_file():
        df = _load_json_file(bronze_path)
    elif bronze_path.is_dir():
        frames = [_load_json_file(f) for f in sorted(bronze_path.rglob("*.json"))]
        if not frames:
            logger.warning("No JSON files found in %s", bronze_path)
            return {"status": "empty", "rows": 0}
        df = pd.concat(frames, ignore_index=True)
    else:
        raise FileNotFoundError(f"Bronze path not found: {bronze_path}")

    if df.empty:
        return {"status": "empty", "rows": 0}

    for col in MW_CAST_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors="coerce").astype(float)  # type: ignore
    df = pd.DataFrame(df)

    existing_renames = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    if existing_renames:
        df = df.rename(columns=existing_renames)

    if "date_heure" in df.columns:
        df["date_heure"] = pd.to_datetime(df["date_heure"], utc=True, errors="coerce")

    before_dedup = len(df)
    if "date_heure" in df.columns:
        df = df.drop_duplicates(subset=["date_heure"], keep="last")
    dupes_removed = before_dedup - len(df)

    df, quality_metrics = apply_quality_rules(df, RTE_QUALITY_RULES, "rte_national")

    files_written = _write_hive_partitioned(df, output_dir, "silver/rte/national")

    summary = {
        "status": "success",
        "input_rows": before_dedup,
        "output_rows": len(df),
        "duplicates_removed": dupes_removed,
        "files_written": files_written,
        "quality": quality_metrics,
    }
    logger.info("National Silver: %d → %d rows, %d dupes removed, %d files",
                before_dedup, len(df), dupes_removed, files_written)
    return summary
