"""
Quality Check Implementations — Story 3.3, Task 1.2

Individual check functions used by the gate runner.
Each returns a CheckResult dict with: name, status (PASS/FAIL/WARN), details.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


def null_check(
    df: pd.DataFrame,
    columns: list[str],
    name: str = "null_check",
) -> dict:
    """
    AC #1: Verify mandatory fields are non-null.

    Returns FAIL if any null found in specified columns.
    """
    nulls = {}
    for col in columns:
        if col not in df.columns:
            nulls[col] = -1  # column missing entirely
            continue
        count = int(df[col].isna().sum())
        if count > 0:
            nulls[col] = count

    status = CheckStatus.FAIL if nulls else CheckStatus.PASS
    return {
        "name": name,
        "check_type": "null_check",
        "status": status.value,
        "details": {"columns_checked": columns, "nulls_found": nulls},
    }


def range_check(
    df: pd.DataFrame,
    column: str,
    min_val: float,
    max_val: float,
    name: str = "range_check",
) -> dict:
    """
    AC #1: Verify values are within expected bounds.

    For France MW values: 0–100,000 MW is reasonable.
    """
    if column not in df.columns:
        return {
            "name": name,
            "check_type": "range_check",
            "status": CheckStatus.FAIL.value,
            "details": {"error": f"Column '{column}' not found"},
        }

    out_of_range = df[(df[column] < min_val) | (df[column] > max_val)]
    count = len(out_of_range)

    status = CheckStatus.FAIL if count > 0 else CheckStatus.PASS
    return {
        "name": name,
        "check_type": "range_check",
        "status": status.value,
        "details": {
            "column": column,
            "min": min_val,
            "max": max_val,
            "out_of_range_count": count,
            "total_rows": len(df),
        },
    }


def row_count_check(
    actual: int,
    expected: int,
    tolerance_pct: float = 5.0,
    name: str = "row_count_check",
) -> dict:
    """
    AC #1: Verify row counts match within tolerance.

    Default tolerance: ±5%.
    """
    if expected == 0:
        status = CheckStatus.PASS if actual == 0 else CheckStatus.WARN
    else:
        diff_pct = abs(actual - expected) / expected * 100
        if diff_pct <= tolerance_pct:
            status = CheckStatus.PASS
        elif diff_pct <= tolerance_pct * 2:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.FAIL

    return {
        "name": name,
        "check_type": "row_count",
        "status": status.value,
        "details": {
            "actual": actual,
            "expected": expected,
            "tolerance_pct": tolerance_pct,
        },
    }


def freshness_check(
    df: pd.DataFrame,
    time_column: str,
    max_age_hours: int = 24,
    reference_time: datetime | None = None,
    name: str = "freshness_check",
) -> dict:
    """
    AC #1: Verify data freshness — latest timestamp within expected window.
    """
    if time_column not in df.columns:
        return {
            "name": name,
            "check_type": "freshness",
            "status": CheckStatus.FAIL.value,
            "details": {"error": f"Column '{time_column}' not found"},
        }

    ref = reference_time or datetime.now(timezone.utc)

    # Get max timestamp
    max_ts = df[time_column].max()
    if max_ts is None or (hasattr(max_ts, '__class__') and pd.isna(max_ts)):
        return {
            "name": name,
            "check_type": "freshness",
            "status": CheckStatus.FAIL.value,
            "details": {"error": "No timestamps found"},
        }

    # Convert to datetime if needed
    if isinstance(max_ts, str):
        max_ts_dt = datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
    elif isinstance(max_ts, datetime):
        max_ts_dt = max_ts
    elif hasattr(max_ts, 'to_pydatetime'):
        # pandas Timestamp
        max_ts_dt = max_ts.to_pydatetime()
    else:
        return {
            "name": name,
            "check_type": "freshness",
            "status": CheckStatus.FAIL.value,
            "details": {"error": f"Unsupported timestamp type: {type(max_ts).__name__}"},
        }

    # Make timezone-aware if needed
    if max_ts_dt.tzinfo is None:
        max_ts_dt = max_ts_dt.replace(tzinfo=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    age = ref - max_ts_dt
    age_hours = age.total_seconds() / 3600

    if age_hours <= max_age_hours:
        status = CheckStatus.PASS
    elif age_hours <= max_age_hours * 2:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL

    return {
        "name": name,
        "check_type": "freshness",
        "status": status.value,
        "details": {
            "latest_timestamp": str(max_ts_dt),
            "age_hours": round(age_hours, 2),
            "max_age_hours": max_age_hours,
        },
    }


def fk_integrity_check(
    conn: Any,
    fact_table: str,
    fk_map: dict[str, str],
    name: str = "fk_integrity",
) -> dict:
    """
    AC #3 (Gold): Verify all FK values exist in DIM tables.
    """
    cursor = conn.cursor()
    orphans = {}

    for fk_col, dim_table in fk_map.items():
        # Use the FK column name as the PK column in the DIM table
        # (id_region matches DIM_REGION.id_region, id_date matches DIM_TIME.id_date, etc.)
        cursor.execute(f"""
            SELECT COUNT(*) FROM {fact_table}
            WHERE {fk_col} NOT IN (SELECT {fk_col} FROM {dim_table})
        """)
        count = cursor.fetchone()[0]
        if count > 0:
            orphans[fk_col] = {"dim_table": dim_table, "orphan_count": count}

    status = CheckStatus.FAIL if orphans else CheckStatus.PASS
    return {
        "name": name,
        "check_type": "fk_integrity",
        "status": status.value,
        "details": {"fk_map": fk_map, "orphans": orphans},
    }


def facteur_charge_check(
    conn: Any,
    name: str = "facteur_charge_range",
) -> dict:
    """
    Gold check: facteur_charge should be between 0 and 1 (or NULL).
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM FACT_ENERGY_FLOW
        WHERE facteur_charge IS NOT NULL
          AND (facteur_charge < 0 OR facteur_charge > 1.5)
    """)
    out_of_range = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM FACT_ENERGY_FLOW WHERE facteur_charge IS NOT NULL")
    total = cursor.fetchone()[0]

    status = CheckStatus.FAIL if out_of_range > 0 else CheckStatus.PASS
    return {
        "name": name,
        "check_type": "facteur_charge_range",
        "status": status.value,
        "details": {
            "out_of_range": out_of_range,
            "total_with_charge": total,
        },
    }
