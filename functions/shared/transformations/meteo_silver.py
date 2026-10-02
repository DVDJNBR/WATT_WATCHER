"""
Météo Silver Transformation — normalizes Open-Meteo records.

Input:  list[dict] from open_meteo_client.fetch_meteo_all_regions()
Output: pandas DataFrame with columns:
        region_code, region_name, timestamp (datetime), temperature_c, wind_speed_10m
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def transform_meteo_to_silver(records: list[dict]) -> pd.DataFrame:
    """
    Normalize raw Open-Meteo records to Silver format.

    Returns:
        DataFrame with columns: region_code, region_name, timestamp,
                                temperature_c, wind_speed_10m
        Empty DataFrame if records is empty.
    """
    if not records:
        logger.info("Météo Silver: no records to transform")
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Parse timestamp — Open-Meteo returns "YYYY-MM-DDTHH:MM" (no tz)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False, errors="coerce")
    df = df.dropna(subset=["timestamp", "temperature_c"])

    logger.info("Météo Silver: %d rows after normalization", len(df))
    return df


def write_meteo_silver(df: pd.DataFrame, output_dir: Path) -> int:
    """
    Write the normalized DataFrame as Hive-partitioned Parquet, same layout
    as era5_silver.py and maintenance_silver.py: silver/meteo/regional/
    year=YYYY/month=MM/data.parquet.

    Returns the number of partition files written (0 if df is empty).
    """
    if df.empty:
        return 0

    df = df.copy()
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.month

    files = 0
    for (year, month), group in df.groupby(["year", "month"]):  # type: ignore[misc]
        out = (
            output_dir / "silver/meteo/regional"
            / f"year={year}" / f"month={month:02d}" / "data.parquet"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns=["year", "month"]).to_parquet(out, index=False)
        files += 1

    logger.info("Météo Silver: wrote %d partition file(s) to %s", files, output_dir)
    return files
