#!/usr/bin/env python3
"""
ETL Pipeline — Bronze → Silver → Gold (local dev)

Reads Bronze JSON files from bronze/rte/production/,
transforms them to Silver Parquet, then loads into Gold SQLite DB (gold.db).

Usage:
    python scripts/run_pipeline.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

from functions.shared.transformations.rte_silver import transform_rte_to_silver
from functions.shared.gold.dim_loader import DimLoader
from functions.shared.gold.fact_loader import FactLoader

BRONZE_BASE = ROOT / "bronze" / "rte" / "production"
SILVER_BASE = ROOT / "silver"
GOLD_DB     = ROOT / "gold.db"


def run() -> None:
    # ── Step 1: Find Bronze files ─────────────────────────────────────────────
    bronze_files = sorted(BRONZE_BASE.rglob("*.json"))
    if not bronze_files:
        logger.error("No Bronze JSON files found in %s", BRONZE_BASE)
        logger.error("Run the ingestion first (RTE API) or drop a JSON file there.")
        sys.exit(1)

    logger.info("📂 Found %d Bronze file(s)", len(bronze_files))

    # ── Step 2: Bronze → Silver ───────────────────────────────────────────────
    SILVER_BASE.mkdir(parents=True, exist_ok=True)
    for bf in bronze_files:
        logger.info("🔄 Transforming: %s", bf.name)
        try:
            result = transform_rte_to_silver(bf, SILVER_BASE)
            logger.info(
                "   ✓ status=%s  rows=%s  quality=%s",
                result.get("status"),
                result.get("rows_written", result.get("rows")),
                result.get("quality_status", "ok"),
            )
        except Exception as exc:
            logger.error("   ✗ Failed: %s", exc)
            raise

    # ── Step 3: Silver → Gold (SQLite) ────────────────────────────────────────
    logger.info("🗄️  Creating Gold DB: %s", GOLD_DB)
    conn = sqlite3.connect(str(GOLD_DB))

    dim  = DimLoader(conn)
    dim.ensure_schema()

    fact = FactLoader(conn)
    result = fact.load_from_silver(SILVER_BASE)

    conn.close()
    logger.info("   ✓ status=%s  rows_loaded=%d", result.get("status"), result.get("rows_loaded", 0))

    # ── Step 4: Verify ────────────────────────────────────────────────────────
    conn = sqlite3.connect(str(GOLD_DB))
    summary = FactLoader(conn).get_fact_summary()
    conn.close()

    print("\n✅ Gold DB prête :")
    for k, v in summary.items():
        print(f"   {k:<22} {v}")
    print(f"\n   → {GOLD_DB}")
    print("\nProchaines étapes :")
    print("   1. python scripts/dev_server.py   (backend local)")
    print("   2. cd frontend && npm run dev      (frontend)")


if __name__ == "__main__":
    run()
