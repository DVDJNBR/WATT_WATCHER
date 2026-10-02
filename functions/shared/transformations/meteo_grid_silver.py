"""
Météo Grid Silver Transformation — normalizes the 352-point Open-Meteo grid.

Input:  list[dict] from open_meteo_client.fetch_meteo_grid()
Output: pandas DataFrame with columns: lat, lon, cloud_cover, wind_speed,
        wind_direction, fetched_at
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def transform_grid_to_silver(records: list[dict]) -> pd.DataFrame:
    """Normalize raw grid records to Silver format. Empty DataFrame if records is empty."""
    if not records:
        logger.info("Météo Grid Silver: no records to transform")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["fetched_at"] = datetime.now(timezone.utc)

    logger.info("Météo Grid Silver: %d rows after normalization", len(df))
    return df


def write_grid_silver(df: pd.DataFrame, output_dir: Path) -> int:
    """
    Overwrite a single Parquet file — no history by design. Unlike every
    other Silver output (partitioned by year/month), the grid only ever
    needs to reflect the latest fetch: partitioning it the same way would
    accumulate 352 rows x 96 cycles/day forever, for a dataset whose only
    consumer (the live map) wants "now", not a time series.

    Returns 1 if a file was written, 0 if df was empty.
    """
    if df.empty:
        return 0

    out = output_dir / "silver/meteo/grid/data.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    logger.info("Météo Grid Silver: wrote %d rows to %s", len(df), out)
    return 1
