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


def run(job_id: str, bronze: Any, silver: Any) -> dict:
    """Fetch ENTSO-E day-ahead prices, Bronze -> Silver -> Gold (fact_market_price)."""
    from shared.transformations.price_silver import transform_price_to_silver
    from shared.gold.dim_loader import DimLoader

    logger.info("[%s] Price: ingestion (ENTSO-E)", job_id)
    try:
        import os
        entsoe_token = os.environ.get("ENTSOE_API_TOKEN", "")
        if not entsoe_token:
            return {"status": "skipped", "reason": "no ENTSOE_API_TOKEN"}

        now = datetime.now(timezone.utc)
        # 26h lookback comfortably covers the current market day regardless of
        # DST offset; ON CONFLICT(id_date) DO UPDATE below makes re-fetching
        # overlapping slots on every run harmless.
        period_start = now - timedelta(hours=26)
        client = EntsoeClient(api_token=entsoe_token)
        price_records = client.fetch_day_ahead_prices(period_start, now)
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

            cursor = conn.cursor()
            rows_loaded = 0
            for _, row in df_price.iterrows():
                ts_str = row["timestamp"].strftime("%Y-%m-%dT%H:%M:00")
                cursor.execute(f"SELECT id_date FROM {tbl_time} WHERE horodatage = {ph}", (ts_str,))
                id_date_r = cursor.fetchone()
                if not id_date_r:
                    continue
                if is_sqlite:
                    cursor.execute(
                        f"""INSERT INTO {tbl_price} (id_date, price_eur_mwh, retrieved_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(id_date) DO UPDATE SET
                                price_eur_mwh = excluded.price_eur_mwh,
                                retrieved_at  = excluded.retrieved_at""",
                        (id_date_r[0], row["price_eur_mwh"], now_str),
                    )
                else:
                    cursor.execute(
                        f"""INSERT INTO {tbl_price} (id_date, price_eur_mwh, retrieved_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (id_date) DO UPDATE SET
                                price_eur_mwh = EXCLUDED.price_eur_mwh,
                                retrieved_at  = EXCLUDED.retrieved_at""",
                        (id_date_r[0], row["price_eur_mwh"], now_str),
                    )
                rows_loaded += 1
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
