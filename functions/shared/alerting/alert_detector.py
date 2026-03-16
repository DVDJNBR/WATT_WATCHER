"""
Alert Detector — Story 5.2

Detects production/consumption crossings from Gold SQL (FACT_ENERGY_FLOW).
Returns alerts for subscribed users — consumed by the story 5.3 timer function.

Distinct from alert_engine.py (Silver Parquet / dashboard alerts).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# SQL: latest timestamp, SUM production across all sources, MAX consumption per region
_SQL = """
    SELECT
        r.code_insee   AS region_code,
        SUM(f.valeur_mw)       AS prod_mw,
        MAX(f.consommation_mw) AS conso_mw
    FROM FACT_ENERGY_FLOW f
    JOIN DIM_REGION r ON f.id_region = r.id_region
    JOIN DIM_TIME t   ON f.id_date   = t.id_date
    WHERE t.horodatage = (
        SELECT MAX(t2.horodatage)
        FROM FACT_ENERGY_FLOW f2
        JOIN DIM_TIME t2 ON f2.id_date = t2.id_date
    )
    GROUP BY r.code_insee
"""


def detect(conn: Any) -> list:
    """
    Detect production/consumption crossings at the latest Gold timestamp.

    Args:
        conn: DB connection (pyodbc or sqlite3).

    Returns:
        List of dicts: [{"region_code": str, "alert_type": str, "prod_mw": float, "conso_mw": float}]
        Only regions with imbalance (prod != conso, conso > 0) are returned.
    """
    cursor = conn.cursor()
    cursor.execute(_SQL)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    alerts = []
    for row in rows:
        r = dict(zip(cols, row))
        conso = r.get("conso_mw")
        prod = r.get("prod_mw")
        region_code = r.get("region_code")

        if conso is None or conso <= 0:
            continue
        if prod is None:
            continue

        if prod < conso:
            alerts.append({
                "region_code": region_code,
                "alert_type": "under_production",
                "prod_mw": float(prod),
                "conso_mw": float(conso),
            })
        elif prod > conso:
            alerts.append({
                "region_code": region_code,
                "alert_type": "over_production",
                "prod_mw": float(prod),
                "conso_mw": float(conso),
            })
        # prod == conso → no alert

    logger.info("AlertDetector: %d alert(s) detected", len(alerts))
    return alerts
