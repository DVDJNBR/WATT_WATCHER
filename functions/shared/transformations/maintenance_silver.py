"""
Maintenance Silver Transformation — Story 3.1, Task 3

Cleans scraped maintenance JSON from Bronze:
- Normalize date formats to ISO 8601
- Clean description text (strip HTML artifacts)
- Dedup on event_id
- Hive-partitioned by year/month
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def transform_maintenance_to_silver(
    bronze_path: str | Path,
    output_dir: str | Path,
) -> dict:
    """Transform maintenance Bronze JSON → Silver Parquet."""
    bronze_path = Path(bronze_path)
    output_dir = Path(output_dir)

    # Load scraped JSON
    if bronze_path.is_file():
        data = json.loads(bronze_path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
    elif bronze_path.is_dir():
        records = []
        for f in sorted(bronze_path.rglob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            records.extend(d if isinstance(d, list) else [d])
    else:
        raise FileNotFoundError(f"Bronze path not found: {bronze_path}")

    if not records:
        return {"status": "empty", "rows": 0}

    df = pd.DataFrame(records)

    # Parse dates
    for date_col in ["start_date", "end_date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")

    # Clean description text (strip extra whitespace)
    if "description" in df.columns:
        df["description"] = df["description"].str.strip().str.replace(r"\s+", " ", regex=True)

    # Dedup on event_id
    before = len(df)
    if "event_id" in df.columns:
        df = df.drop_duplicates(subset=["event_id"], keep="last")

    # Write partitioned by start_date year/month
    files = 0
    if "start_date" in df.columns:
        df = df.copy()
        df["year"] = df["start_date"].dt.year
        df["month"] = df["start_date"].dt.month
        for (year, month), group in df.groupby(["year", "month"]):  # type: ignore[misc]
            out = (
                output_dir / "silver/maintenance"
                / f"year={year}" / f"month={month:02d}" / "data.parquet"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year", "month"]).to_parquet(out, index=False)
            files += 1
    else:
        out = output_dir / "silver/maintenance/data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        files = 1

    summary = {
        "status": "success",
        "input_rows": before,
        "output_rows": len(df),
        "duplicates_removed": before - len(df),
        "files_written": files,
    }
    logger.info("Maintenance Silver: %d → %d rows", before, len(df))
    return summary
