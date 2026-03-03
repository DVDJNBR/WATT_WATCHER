"""
ERA5 Silver Transformation — Story 3.1, Task 4

Cleans ERA5 Bronze Parquet:
- Standardize column names
- Ensure wind_speed_100m is computed (if not already)
- Apply quality rules
- Output Hive-partitioned by year/month
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from functions.shared.transformations.data_quality import (
    ERA5_QUALITY_RULES,
    apply_quality_rules,
)

logger = logging.getLogger(__name__)


def transform_era5_to_silver(
    bronze_path: str | Path,
    output_dir: str | Path,
) -> dict:
    """Transform ERA5 Bronze Parquet → Silver Parquet."""
    bronze_path = Path(bronze_path)
    output_dir = Path(output_dir)

    # Load Bronze Parquet
    if bronze_path.is_file():
        df = pd.read_parquet(bronze_path)
    elif bronze_path.is_dir():
        parquets = sorted(bronze_path.rglob("*.parquet"))
        if not parquets:
            return {"status": "empty", "rows": 0}
        df = pd.concat([pd.read_parquet(f) for f in parquets], ignore_index=True)
    else:
        raise FileNotFoundError(f"Bronze path not found: {bronze_path}")

    # Ensure derived fields exist
    if "wind_speed_100m" not in df.columns and "u100" in df.columns:
        df["wind_speed_100m"] = (df["u100"] ** 2 + df["v100"] ** 2) ** 0.5

    if "temperature_c" not in df.columns and "t2m" in df.columns:
        df["temperature_c"] = (df["t2m"] - 273.15).round(2)

    # Apply quality rules
    df, quality = apply_quality_rules(df, ERA5_QUALITY_RULES, "era5_climate")

    # Dedup on region + time
    before = len(df)
    dedup_cols = [c for c in ["region_code", "valid_time"] if c in df.columns]
    if len(dedup_cols) == 2:
        df = df.drop_duplicates(subset=dedup_cols, keep="last")

    # Write Hive-partitioned by year/month
    time_col = "valid_time" if "valid_time" in df.columns else None
    files = 0

    if time_col:
        df = df.copy()
        df["year"] = df[time_col].dt.year
        df["month"] = df[time_col].dt.month
        for (year, month), group in df.groupby(["year", "month"]):
            out = (
                output_dir / "silver/climate/era5"
                / f"year={year}" / f"month={month:02d}" / "data.parquet"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year", "month"]).to_parquet(out, index=False)
            files += 1
    else:
        out = output_dir / "silver/climate/era5/data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        files = 1

    summary = {
        "status": "success",
        "input_rows": before,
        "output_rows": len(df),
        "files_written": files,
        "quality": quality,
    }
    logger.info("ERA5 Silver: %d → %d rows, %d files", before, len(df), files)
    return summary
