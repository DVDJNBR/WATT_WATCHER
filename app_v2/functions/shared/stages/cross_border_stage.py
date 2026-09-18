"""ENTSO-E cross-border physical flow stage — part of the daily pipeline.

Physical flow (A11) is reported per direction, always as a positive
quantity — there's no "negative export" in the raw data. For each of
France's four RTE-reported borders (GB, CH, IT, ES — see
entsoe_client.BORDER_DOMAINS), this fetches both directions and nets them
into a single flow_mw per timestamp: positive = France exporting, negative
= France importing. Same cadence as prices/outages (published once a day,
checking more often gains nothing).
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.db import get_db_connection
from shared.entsoe_client import BORDER_DOMAINS, FRANCE_DOMAIN, EntsoeClient, EntsoeClientError

logger = logging.getLogger(__name__)


def _net_flows(client: EntsoeClient, border_domain: str, period_start: datetime, period_end: datetime) -> dict[datetime, float]:
    """Fetch both directions for one border and return {timestamp: net_mw}."""
    export_records = client.fetch_cross_border_physical_flow(
        FRANCE_DOMAIN, border_domain, period_start, period_end
    )
    import_records = client.fetch_cross_border_physical_flow(
        border_domain, FRANCE_DOMAIN, period_start, period_end
    )
    export_by_ts = {r["timestamp"]: r["flow_mw"] for r in export_records}
    import_by_ts = {r["timestamp"]: r["flow_mw"] for r in import_records}
    all_ts = set(export_by_ts) | set(import_by_ts)
    return {ts: export_by_ts.get(ts, 0.0) - import_by_ts.get(ts, 0.0) for ts in all_ts}


def run(
    job_id: str, bronze: Any, silver: Any,
    period_start: datetime | None = None, period_end: datetime | None = None,
) -> dict:
    """Fetch ENTSO-E cross-border flows, Bronze -> Silver -> Gold (fact_cross_border_flow)."""
    import os

    import pandas as pd
    from shared.gold.dim_loader import DimLoader

    logger.info("[%s] Cross-border flow: ingestion (ENTSO-E)", job_id)
    try:
        entsoe_token = os.environ.get("ENTSOE_API_TOKEN", "")
        if not entsoe_token:
            return {"status": "skipped", "reason": "no ENTSOE_API_TOKEN"}

        now = datetime.now(timezone.utc)
        if period_end is None:
            period_end = now
        if period_start is None:
            period_start = period_end - timedelta(hours=26)

        client = EntsoeClient(api_token=entsoe_token)

        records: list[dict] = []
        for border_code, border_domain in BORDER_DOMAINS.items():
            try:
                net = _net_flows(client, border_domain, period_start, period_end)
            except EntsoeClientError as exc:
                # One bad border domain code shouldn't take down the other three.
                logger.warning("[%s] Cross-border flow: %s failed (%s), skipping", job_id, border_code, exc)
                continue
            for ts, flow_mw in net.items():
                records.append({"timestamp": ts, "border_code": border_code, "flow_mw": round(flow_mw, 1)})

        if records:
            bronze.write_json(
                [{**r, "timestamp": r["timestamp"].isoformat()} for r in records],
                source="cross_border_flow",
            )

        if not records:
            return {"status": "empty", "rows": 0}

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df_part = df.copy()
        df_part["year"] = df_part["timestamp"].dt.year
        df_part["month"] = df_part["timestamp"].dt.month
        silver.write_parquet(df_part, source="cross_border_flow", partition_cols=["year", "month"])

        conn = get_db_connection()
        try:
            dim = DimLoader(conn)
            dim.ensure_schema()
            timestamps = df["timestamp"].apply(lambda t: t.strftime("%Y-%m-%dT%H:%M:00")).tolist()
            dim.upsert_time(timestamps)

            is_sqlite = isinstance(conn, sqlite3.Connection)
            tbl_flow = "FACT_CROSS_BORDER_FLOW" if is_sqlite else "fact_cross_border_flow"
            tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
            now_str = now.isoformat()

            CHUNK = 500
            cursor = conn.cursor()
            row_list = list(df.iterrows())
            id_date_by_ts: dict[str, int] = {}
            for i in range(0, len(row_list), CHUNK):
                chunk_ts = [row["timestamp"].strftime("%Y-%m-%dT%H:%M:00") for _, row in row_list[i:i + CHUNK]]
                if is_sqlite:
                    placeholders = ",".join(["?"] * len(chunk_ts))
                    cursor.execute(
                        f"SELECT id_date, horodatage FROM {tbl_time} WHERE horodatage IN ({placeholders})",
                        chunk_ts,
                    )
                else:
                    cursor.execute(
                        f"SELECT id_date, horodatage FROM {tbl_time} WHERE horodatage = ANY(%s::timestamptz[])",
                        (chunk_ts,),
                    )
                for id_date, horodatage in cursor.fetchall():
                    key = horodatage.strftime("%Y-%m-%dT%H:%M:00") if hasattr(horodatage, "strftime") else horodatage
                    id_date_by_ts[key] = id_date

            upsert_rows = [
                (id_date_by_ts[ts_str], row["border_code"], row["flow_mw"], now_str)
                for _, row in row_list
                if (ts_str := row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")) in id_date_by_ts
            ]

            if is_sqlite:
                cursor.executemany(
                    f"""INSERT INTO {tbl_flow} (id_date, border_code, flow_mw, retrieved_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id_date, border_code) DO UPDATE SET
                            flow_mw      = excluded.flow_mw,
                            retrieved_at = excluded.retrieved_at""",
                    upsert_rows,
                )
            else:
                from psycopg2.extras import execute_values
                execute_values(
                    cursor,
                    f"""INSERT INTO {tbl_flow} (id_date, border_code, flow_mw, retrieved_at)
                        VALUES %s
                        ON CONFLICT (id_date, border_code) DO UPDATE SET
                            flow_mw      = EXCLUDED.flow_mw,
                            retrieved_at = EXCLUDED.retrieved_at""",
                    upsert_rows,
                )
            rows_loaded = len(upsert_rows)
            conn.commit()
            logger.info("[%s] Cross-border flow: %d rows loaded", job_id, rows_loaded)
            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except EntsoeClientError as exc:
        logger.warning("[%s] Cross-border flow stage failed (non-fatal): %s", job_id, exc)
        return {"status": "failure", "error": str(exc)}
    except Exception as exc:
        logger.error("[%s] Cross-border flow stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
