"""
Data Quality Framework — Story 3.1, Task 5

Defines null handling strategies per column and provides
quality metrics logging for the Silver transformation layer.

Strategies:
- DROP: Remove the entire row
- FILL_ZERO: Replace null with 0.0
- FORWARD_FILL: Use previous valid value
- FLAG: Keep the null but add a _quality_flag column
"""

import logging
from enum import Enum
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)


class NullStrategy(str, Enum):
    """How to handle null values."""
    DROP = "drop"
    FILL_ZERO = "fill_zero"
    FORWARD_FILL = "forward_fill"
    FLAG = "flag"


# Default quality rules per source domain
# MW columns use FLAG (not FILL_ZERO) — RTE returns null for time slots not yet
# published ("données temps réel" arrives with ~15 min delay). Replacing null
# with 0 would be misleading: it looks like zero production, not missing data.
# fact_loader.py skips null MW values so FACT only contains real measurements.
RTE_QUALITY_RULES: dict[str, NullStrategy] = {
    "consommation_mw": NullStrategy.FLAG,
    "nucleaire_mw": NullStrategy.FLAG,
    "eolien_mw": NullStrategy.FLAG,
    "solaire_mw": NullStrategy.FLAG,
    "hydraulique_mw": NullStrategy.FLAG,
    "gaz_mw": NullStrategy.FLAG,
    "charbon_mw": NullStrategy.FLAG,
    "bioenergies_mw": NullStrategy.FLAG,
    "fioul_mw": NullStrategy.FLAG,
    "pompage_mw": NullStrategy.FLAG,
    "date_heure": NullStrategy.DROP,
    "code_insee_region": NullStrategy.DROP,
}

CAPACITY_QUALITY_RULES: dict[str, NullStrategy] = {
    "code_insee_region": NullStrategy.DROP,
    "puissance_installee_mw": NullStrategy.FILL_ZERO,
}

ERA5_QUALITY_RULES: dict[str, NullStrategy] = {
    "wind_speed_100m": NullStrategy.FILL_ZERO,
    "temperature_c": NullStrategy.FORWARD_FILL,
    "ssrd": NullStrategy.FILL_ZERO,
}


def apply_quality_rules(
    df: pd.DataFrame,
    rules: dict[str, NullStrategy],
    source_name: str = "",
) -> tuple[pd.DataFrame, dict]:
    """
    Apply null handling rules to a DataFrame.

    Args:
        df: Input DataFrame.
        rules: Column → NullStrategy mapping.
        source_name: Source identifier for logging.

    Returns:
        Tuple of (cleaned DataFrame, quality metrics dict).
    """
    df = df.copy()

    metrics = {
        "source": source_name,
        "input_rows": len(df),
        "nulls_found": {},
        "rows_dropped": 0,
        "values_filled": 0,
        "values_flagged": 0,
    }

    # Count nulls per column before cleaning
    for col in rules:
        if col in df.columns:
            null_count = int(df[col].isna().sum())
            if null_count > 0:
                metrics["nulls_found"][col] = null_count

    # Apply strategies
    drop_cols = [col for col, strategy in rules.items()
                 if strategy == NullStrategy.DROP and col in df.columns]
    if drop_cols:
        before = len(df)
        df = df.dropna(subset=drop_cols)
        metrics["rows_dropped"] = before - len(df)

    fill_zero_cols = [col for col, strategy in rules.items()
                      if strategy == NullStrategy.FILL_ZERO and col in df.columns]
    for col in fill_zero_cols:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            df[col] = df[col].fillna(0.0)
            metrics["values_filled"] += null_count

    ffill_cols = [col for col, strategy in rules.items()
                  if strategy == NullStrategy.FORWARD_FILL and col in df.columns]
    for col in ffill_cols:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            df[col] = df[col].ffill()
            metrics["values_filled"] += null_count

    flag_cols = [col for col, strategy in rules.items()
                 if strategy == NullStrategy.FLAG and col in df.columns]
    for col in flag_cols:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            df[f"{col}_is_null"] = df[col].isna()
            metrics["values_flagged"] += null_count

    metrics["output_rows"] = len(df)

    logger.info(
        "Quality [%s]: %d→%d rows, %d dropped, %d filled, %d flagged",
        source_name, metrics["input_rows"], metrics["output_rows"],
        metrics["rows_dropped"], metrics["values_filled"], metrics["values_flagged"],
    )

    return df, metrics
