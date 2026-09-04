"""
Recalibrate the surplus/curtailment threshold against real pipeline data — FT/PRICES follow-up.

Standalone, read-only analysis script — deliberately NOT an Azure Function.
Replaces the one-time manual exercise documented in
docs/entsoe_price_integration_report.md section 4 (a day-level cross-check
against 63 manually-extracted 2025 negative-price days) with a reproducible
query against fact_market_price + fact_energy_flow, now that both are native
to the pipeline (see scripts/backfill_market_prices.py for how
fact_market_price got its history).

National ratio, replicated exactly from frontend/src/components/ProdConsChart.jsx:
    prod = sum of all positive source values, across every region, for a timestamp
    conso = national consumption (regional consommation_mw values summed once
            per region, not once per source row — it's duplicated across a
            region's source rows in fact_energy_flow)
    ratio = (prod - conso) / conso

Timestamps where fewer than all currently-reporting regions have data are
excluded (RTE publishes region-by-region with a short delay; summing an
incomplete region set creates an artificial spike) — same completeness
guard DashboardPage.jsx applies client-side.

This is finer-grained than the original manual calibration: that worked at
day level ("did this day trigger, was this day negative"); this works at
the actual 15-min slot level the live signal itself evaluates, since
fact_market_price is now published at matching granularity.

Usage:
    uv run python scripts/recalibrate_surplus_threshold.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

from shared.db import get_db_connection

logger = logging.getLogger(__name__)

THRESHOLDS = [0.05, 0.20, 0.30, 0.40, 0.50]

QUERY = """
WITH region_cons AS (
    SELECT id_date, id_region, AVG(consommation_mw) AS cons_mw
    FROM fact_energy_flow
    GROUP BY id_date, id_region
),
national_prod AS (
    SELECT id_date,
           SUM(CASE WHEN valeur_mw > 0 THEN valeur_mw ELSE 0 END) AS prod_mw,
           COUNT(DISTINCT id_region) AS region_count
    FROM fact_energy_flow
    GROUP BY id_date
),
national_cons AS (
    SELECT id_date, SUM(cons_mw) AS conso_mw
    FROM region_cons
    GROUP BY id_date
)
SELECT t.horodatage, np.prod_mw, nc.conso_mw, p.price_eur_mwh
FROM national_prod np
JOIN national_cons nc ON np.id_date = nc.id_date
JOIN dim_time t ON np.id_date = t.id_date
JOIN fact_market_price p ON np.id_date = p.id_date
WHERE np.region_count = (SELECT MAX(region_count) FROM national_prod)
  AND nc.conso_mw > 0
ORDER BY t.horodatage;
"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(QUERY)
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        logger.info("No overlapping fact_market_price / fact_energy_flow rows yet.")
        return

    n = len(rows)
    negative_price = [price < 0 for _, _, _, price in rows]
    n_negative = sum(negative_price)
    logger.info(
        "%d matched 15-min slots, %s -> %s (%d with a negative price, %.1f%%)",
        n, rows[0][0], rows[-1][0], n_negative, 100 * n_negative / n,
    )

    logger.info("")
    logger.info(
        "%-8s %10s %14s %10s",
        "Seuil", "Déclenché", "Précision", "Rappel",
    )
    for threshold in THRESHOLDS:
        triggered = [(prod - conso) / conso > threshold for _, prod, conso, _ in rows]
        n_triggered = sum(triggered)
        true_positives = sum(t and neg for t, neg in zip(triggered, negative_price))
        precision = true_positives / n_triggered if n_triggered else float("nan")
        recall = true_positives / n_negative if n_negative else float("nan")
        logger.info(
            "%-8s %9.1f%% %13.1f%% %9.1f%%",
            f"{int(threshold * 100)}%", 100 * n_triggered / n, 100 * precision, 100 * recall,
        )


if __name__ == "__main__":
    main()
