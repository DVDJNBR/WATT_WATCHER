"""
Generation unit outages stage — part of the daily pipeline.

Replaces the old RTE HTML scraper (shared/maintenance_scraper.py, removed):
that scraper's MAINTENANCE_SCRAPING_URL was never actually wired into
Terraform, so it never ran a single time in production. ENTSO-E's own
Unavailability of Production Units feed (A77) is real, structured, and
reuses credentials/infra we already have for day-ahead prices.

Still lands in fact_maintenance (same table/columns as before) — the
column name `scraped_at` is a bit of a misnomer now (nothing is scraped
any more), kept as-is to avoid a schema migration; it just means "when we
last confirmed this from ENTSO-E".
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.db import get_db_connection
from shared.entsoe_client import EntsoeClient, EntsoeClientError

logger = logging.getLogger(__name__)


def run(job_id: str, bronze: Any, silver: Any) -> dict:
    """Fetch ENTSO-E generation outages, Bronze -> Silver -> Gold (fact_maintenance)."""
    import pandas as pd
    from shared.gold.dim_loader import DimLoader
    from shared.transformations.maintenance_silver import clean_maintenance_df

    logger.info("[%s] Outages: ingestion (ENTSO-E)", job_id)
    try:
        entsoe_token = os.environ.get("ENTSOE_API_TOKEN", "")
        if not entsoe_token:
            return {"status": "skipped", "reason": "no ENTSOE_API_TOKEN"}

        now = datetime.now(timezone.utc)
        # Wide window on purpose: outage periods can span weeks (a refuelling
        # stop), and this runs once a day — we want both what's active right
        # now and what's already been announced for the near future.
        period_start = now - timedelta(days=1)
        period_end = now + timedelta(days=60)

        client = EntsoeClient(api_token=entsoe_token)
        outage_events = client.fetch_unavailability_of_production_units(period_start, period_end)

        if outage_events:
            bronze.write_json(
                [
                    {**e, "start_date": e["start_date"].isoformat(), "end_date": e["end_date"].isoformat()}
                    for e in outage_events
                ],
                source="outages",
            )

        df_outages = clean_maintenance_df(pd.DataFrame(outage_events))

        if df_outages.empty:
            return {"status": "empty", "rows": 0}

        if "start_date" in df_outages.columns:
            df_part = df_outages.copy()
            df_part["year"] = df_part["start_date"].dt.year
            df_part["month"] = df_part["start_date"].dt.month
            silver.write_parquet(df_part, source="outages", partition_cols=["year", "month"])
        else:
            silver.write_parquet(df_outages, source="outages")

        conn = get_db_connection()
        try:
            dim = DimLoader(conn)
            dim.ensure_schema()

            is_sqlite = isinstance(conn, sqlite3.Connection)
            tbl_maintenance = "FACT_MAINTENANCE" if is_sqlite else "fact_maintenance"
            now_str = now.isoformat()

            def _iso(val):
                return val.isoformat() if pd.notna(val) else None

            cursor = conn.cursor()
            rows_loaded = 0
            for evt in df_outages.to_dict("records"):
                event_id = str(evt.get("event_id", "")).strip()
                if not event_id:
                    continue
                if is_sqlite:
                    cursor.execute(
                        f"""INSERT INTO {tbl_maintenance}
                                (event_id, unit_name, event_type,
                                 start_date, end_date, unavailable_mw, scraped_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(event_id) DO UPDATE SET
                                unit_name      = excluded.unit_name,
                                event_type     = excluded.event_type,
                                start_date     = excluded.start_date,
                                end_date       = excluded.end_date,
                                unavailable_mw = excluded.unavailable_mw,
                                scraped_at     = excluded.scraped_at""",
                        (
                            event_id, evt.get("unit_name"), evt.get("event_type"),
                            _iso(evt.get("start_date")), _iso(evt.get("end_date")),
                            evt.get("unavailable_mw"), now_str,
                        ),
                    )
                else:
                    cursor.execute(
                        f"""INSERT INTO {tbl_maintenance}
                                (event_id, unit_name, event_type,
                                 start_date, end_date, unavailable_mw, scraped_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (event_id) DO UPDATE SET
                                unit_name      = EXCLUDED.unit_name,
                                event_type     = EXCLUDED.event_type,
                                start_date     = EXCLUDED.start_date,
                                end_date       = EXCLUDED.end_date,
                                unavailable_mw = EXCLUDED.unavailable_mw,
                                scraped_at     = EXCLUDED.scraped_at""",
                        (
                            event_id, evt.get("unit_name"), evt.get("event_type"),
                            _iso(evt.get("start_date")), _iso(evt.get("end_date")),
                            evt.get("unavailable_mw"), now_str,
                        ),
                    )
                rows_loaded += 1
            conn.commit()
            logger.info("[%s] Outages: %d rows loaded", job_id, rows_loaded)
            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except EntsoeClientError as exc:
        logger.warning("[%s] Outages stage failed (non-fatal): %s", job_id, exc)
        return {"status": "failure", "error": str(exc)}
    except Exception as exc:
        logger.error("[%s] Outages stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
