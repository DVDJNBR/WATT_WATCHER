"""ENTSO-E day-ahead price stage — part of the daily pipeline.

Day-ahead prices are published once a day (around midday, for the whole
following day) — checking every 15 minutes never caught anything a daily
check wouldn't, so this moved out of the 15-minute pipeline.
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.db import get_db_connection
from shared.entsoe_client import EntsoeClient, EntsoeClientError

logger = logging.getLogger(__name__)


def run(
    job_id: str, bronze: Any, silver: Any,
    period_start: datetime | None = None, period_end: datetime | None = None,
) -> dict:
    """
    Fetch ENTSO-E day-ahead prices, Bronze -> Silver -> Gold (fact_market_price).

    period_start/period_end default to the normal 26h lookback (the live
    pipeline_daily call), but can be widened for a manual historical backfill
    (see scripts/backfill_market_prices.py) — same Bronze/Silver/Gold path
    either way, only the fetch window differs.
    """
    from shared.transformations.price_silver import transform_price_to_silver
    from shared.gold.dim_loader import DimLoader

    logger.info("[%s] Price: ingestion (ENTSO-E)", job_id)
    try:
        import os
        entsoe_token = os.environ.get("ENTSOE_API_TOKEN", "")
        if not entsoe_token:
            return {"status": "skipped", "reason": "no ENTSOE_API_TOKEN"}

        now = datetime.now(timezone.utc)
        if period_end is None:
            period_end = now
        if period_start is None:
            # 26h lookback comfortably covers the current market day regardless
            # of DST offset; ON CONFLICT(id_date) DO UPDATE below makes
            # re-fetching overlapping slots on every run harmless.
            period_start = period_end - timedelta(hours=26)
        client = EntsoeClient(api_token=entsoe_token)
        price_records = client.fetch_day_ahead_prices(period_start, period_end)
        if price_records:
            bronze.write_json(
                [
                    {"timestamp": r["timestamp"].isoformat(), "price_eur_mwh": r["price_eur_mwh"]}
                    for r in price_records
                ],
                source="price",
            )
        df_price = transform_price_to_silver(price_records)

        if df_price.empty:
            return {"status": "empty", "rows": 0}

        df_price_part = df_price.copy()
        df_price_part["year"] = df_price_part["timestamp"].dt.year
        df_price_part["month"] = df_price_part["timestamp"].dt.month
        silver.write_parquet(
            df_price_part, source="price", sub_path="market",
            partition_cols=["year", "month"],
        )

        conn = get_db_connection()
        try:
            dim = DimLoader(conn)
            dim.ensure_schema()
            timestamps = df_price["timestamp"].apply(lambda t: t.strftime("%Y-%m-%dT%H:%M:00")).tolist()
            dim.upsert_time(timestamps)

            is_sqlite = isinstance(conn, sqlite3.Connection)
            ph = "?" if is_sqlite else "%s"
            tbl_price = "FACT_MARKET_PRICE" if is_sqlite else "fact_market_price"
            tbl_time = "DIM_TIME" if is_sqlite else "dim_time"
            now_str = now.isoformat()

            # Batched in chunks rather than one round trip per row — a small
            # 26h-lookback run (~100 rows) never noticed, but a historical
            # backfill (thousands of rows) turned "N rows" into "2N sequential
            # network round trips to Supabase" and looked hung for minutes.
            CHUNK = 500
            cursor = conn.cursor()
            row_list = list(df_price.iterrows())
            id_date_by_ts: dict[str, int] = {}
            for i in range(0, len(row_list), CHUNK):
                chunk_ts = [
                    row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")
                    for _, row in row_list[i:i + CHUNK]
                ]
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
                (id_date_by_ts[ts_str], row["price_eur_mwh"], now_str)
                for _, row in row_list
                if (ts_str := row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")) in id_date_by_ts
            ]

            if is_sqlite:
                # No network latency locally — a plain per-row loop is fine.
                cursor.executemany(
                    f"""INSERT INTO {tbl_price} (id_date, price_eur_mwh, retrieved_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(id_date) DO UPDATE SET
                            price_eur_mwh = excluded.price_eur_mwh,
                            retrieved_at  = excluded.retrieved_at""",
                    upsert_rows,
                )
            else:
                # executemany() is just a client-side loop of execute() in
                # psycopg2 — no fewer round trips than the original code.
                # execute_values() sends a real multi-row VALUES list.
                from psycopg2.extras import execute_values
                execute_values(
                    cursor,
                    f"""INSERT INTO {tbl_price} (id_date, price_eur_mwh, retrieved_at)
                        VALUES %s
                        ON CONFLICT (id_date) DO UPDATE SET
                            price_eur_mwh = EXCLUDED.price_eur_mwh,
                            retrieved_at  = EXCLUDED.retrieved_at""",
                    upsert_rows,
                )
            rows_loaded = len(upsert_rows)
            conn.commit()
            logger.info("[%s] Price: %d rows loaded", job_id, rows_loaded)
            return {"status": "success", "rows": rows_loaded}
        finally:
            conn.close()

    except EntsoeClientError as exc:
        logger.warning("[%s] Price stage failed (non-fatal): %s", job_id, exc)
        return {"status": "failure", "error": str(exc)}
    except Exception as exc:
        logger.error("[%s] Price stage failed: %s", job_id, exc, exc_info=True)
        return {"status": "failure", "error": str(exc)}
