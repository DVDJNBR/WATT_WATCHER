"""
Prix marché Silver Transformation — normalizes ENTSO-E day-ahead price records.

Input:  list[dict] from entsoe_client.EntsoeClient.fetch_day_ahead_prices()
Output: pandas DataFrame with columns: timestamp (tz-aware datetime), price_eur_mwh
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def transform_price_to_silver(records: list[dict]) -> pd.DataFrame:
    """
    Normalize raw ENTSO-E price records to Silver format.

    Returns:
        DataFrame with columns: timestamp, price_eur_mwh — one row per market
        time unit, deduplicated on timestamp (keeping the most recently
        parsed value, in case overlapping fetch windows return the same
        slot twice). Empty DataFrame if records is empty.
    """
    if not records:
        logger.info("Prix marché Silver: no records to transform")
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.dropna(subset=["timestamp", "price_eur_mwh"])
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info("Prix marché Silver: %d rows after normalization", len(df))
    return df
