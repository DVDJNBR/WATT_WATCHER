"""
Météo Silver Transformation — normalizes Open-Meteo records.

Input:  list[dict] from open_meteo_client.fetch_meteo_all_regions()
Output: pandas DataFrame with columns:
        region_code, region_name, timestamp (datetime), temperature_c, wind_speed_10m
"""

import logging

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
