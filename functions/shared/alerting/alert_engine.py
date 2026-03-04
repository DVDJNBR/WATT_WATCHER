"""
Alert Engine — Story 5.2, Task 1

Evaluates over-production and negative-price-risk rules against
the latest Silver Parquet data, which contains both production
source columns and consommation_mw.

Thresholds are configurable via environment variables:
  OVERPRODUCTION_THRESHOLD   — default 1.10 (110 %)
  NEGATIVE_PRICE_THRESHOLD   — default 1.05 (105 %)
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Production source columns present in Silver Parquet
PRODUCTION_COLS = [
    "nucleaire_mw", "eolien_mw", "solaire_mw", "hydraulique_mw",
    "gaz_mw", "charbon_mw", "fioul_mw", "bioenergies_mw",
]

# Hours considered low-demand (00:00–07:59, 22:00–23:59)
LOW_DEMAND_HOURS = set(range(0, 8)) | set(range(22, 24))


def _get_threshold(env_var: str, default: float) -> float:
    try:
        return float(os.environ.get(env_var, default))
    except (TypeError, ValueError):
        return default


def _read_latest_silver(silver_path: Path) -> pd.DataFrame:
    """Load the most-recent Silver Parquet(s) from a directory or single file."""
    if silver_path.is_file():
        return pd.read_parquet(silver_path)
    parquets = sorted(silver_path.rglob("*.parquet"))
    if not parquets:
        return pd.DataFrame()
    # Keep only the most recent partition (last file alphabetically = most recent date)
    return pd.read_parquet(parquets[-1])


def evaluate(silver_path: str | Path) -> list[dict[str, Any]]:
    """
    Evaluate alert rules against the latest Silver data.

    AC #1: Over-production ratio > threshold → CRITICAL alert.
    AC #3: Thresholds configurable via env vars.
    AC #4: Negative price risk when ratio > neg-price threshold in low-demand hours.

    Args:
        silver_path: Path to Silver Parquet file or directory.

    Returns:
        List of alert dicts (may be empty).
    """
    overproduction_threshold = _get_threshold("OVERPRODUCTION_THRESHOLD", 1.10)
    negative_price_threshold = _get_threshold("NEGATIVE_PRICE_THRESHOLD", 1.05)

    path = Path(silver_path)
    df = _read_latest_silver(path)
    if df.empty:
        logger.info("Alert engine: no Silver data found at %s", path)
        return []

    # Keep only rows that have consommation and at least one production col
    prod_present = [c for c in PRODUCTION_COLS if c in df.columns]
    if not prod_present or "consommation_mw" not in df.columns:
        logger.warning("Alert engine: missing required columns in Silver data")
        return []

    id_cols = [c for c in ["date_heure", "code_insee_region", "libelle_region"] if c in df.columns]

    df = df[id_cols + prod_present + ["consommation_mw"]].copy()
    df = df[df["consommation_mw"].notna() & (df["consommation_mw"] > 0)]  # type: ignore[union-attr]

    # Sum all production sources per row
    df["production_total_mw"] = df[prod_present].sum(axis=1)
    df["ratio"] = df["production_total_mw"] / df["consommation_mw"]

    # Extract hour for low-demand detection
    if "date_heure" in df.columns:
        df["_hour"] = pd.to_datetime(df["date_heure"], utc=True, errors="coerce").dt.hour  # type: ignore[union-attr]
    else:
        df["_hour"] = 12

    alerts: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in df.to_dict("records"):  # type: ignore[call-overload]
        ratio = row["ratio"]
        if ratio is None:
            continue

        region = row.get("code_insee_region", "unknown")
        region_label = row.get("libelle_region", region)
        hour = row.get("_hour", 12)
        ts = str(row.get("date_heure", now))

        # AC #1: Over-production
        if ratio > overproduction_threshold:
            alerts.append(_make_alert(
                alert_type="OVERPRODUCTION",
                severity="CRITICAL",
                region=region,
                region_label=region_label,
                timestamp=now,
                data_timestamp=ts,
                details=(
                    f"Production totale ({row['production_total_mw']:.0f} MW) "
                    f"dépasse la consommation de {(ratio - 1) * 100:.1f}% "
                    f"(ratio {ratio:.2f}, seuil {overproduction_threshold:.2f})"
                ),
                ratio=ratio,
            ))

        # AC #4: Negative price risk
        elif ratio > negative_price_threshold and hour in LOW_DEMAND_HOURS:
            alerts.append(_make_alert(
                alert_type="NEGATIVE_PRICE_RISK",
                severity="WARNING",
                region=region,
                region_label=region_label,
                timestamp=now,
                data_timestamp=ts,
                details=(
                    f"Risque de prix négatif : surproduction ({ratio:.2f}) "
                    f"pendant une période de faible demande (h={hour:02d}h)"
                ),
                ratio=ratio,
            ))

    logger.info("Alert engine: %d alert(s) generated from %s", len(alerts), path)
    return alerts


def _make_alert(
    alert_type: str,
    severity: str,
    region: str,
    region_label: str,
    timestamp: str,
    data_timestamp: str,
    details: str,
    ratio: float,
) -> dict[str, Any]:
    return {
        "alert_id": str(uuid.uuid4()),
        "type": alert_type,
        "severity": severity,
        "region": region,
        "region_label": region_label,
        "timestamp": timestamp,
        "data_timestamp": data_timestamp,
        "details": details,
        "ratio": round(ratio, 4),
        "acknowledged": False,
    }
