"""Tests for price_retention.py — FT/PRICES."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from functions.shared.gold.dim_loader import DimLoader
from functions.shared.price_retention import DEFAULT_RETENTION_DAYS, purge_old_prices


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    DimLoader(conn).ensure_schema()
    return conn


def _insert_price(conn, horodatage: str, price: float = 42.0):
    dim = DimLoader(conn)
    dim.upsert_time([horodatage])
    id_date = dim.get_time_id(horodatage)
    conn.execute(
        "INSERT INTO FACT_MARKET_PRICE (id_date, price_eur_mwh, retrieved_at) VALUES (?, ?, ?)",
        (id_date, price, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


class TestPurgeOldPrices:
    def test_deletes_only_old_rows(self, db):
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:00+00:00")
        recent_ts = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00+00:00")
        _insert_price(db, old_ts)
        _insert_price(db, recent_ts)

        deleted = purge_old_prices(db, retention_days=7)

        assert deleted == 1
        remaining = db.execute("SELECT COUNT(*) FROM FACT_MARKET_PRICE").fetchone()[0]
        assert remaining == 1

    def test_does_not_touch_dim_time(self, db):
        """Purging FACT_MARKET_PRICE must never delete DIM_TIME rows — other
        fact tables (FACT_ENERGY_FLOW, ...) still reference them."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:00+00:00")
        _insert_price(db, old_ts)

        purge_old_prices(db, retention_days=7)

        dim_time_count = db.execute("SELECT COUNT(*) FROM DIM_TIME").fetchone()[0]
        assert dim_time_count == 1

    def test_nothing_to_purge_returns_zero(self, db):
        now = datetime.now(timezone.utc)
        recent_ts = now.strftime("%Y-%m-%dT%H:%M:00+00:00")
        _insert_price(db, recent_ts)

        deleted = purge_old_prices(db, retention_days=7)
        assert deleted == 0

    def test_default_retention_from_env(self, db, monkeypatch):
        monkeypatch.setenv("PRICE_RETENTION_DAYS", "1")
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:00+00:00")
        _insert_price(db, old_ts)

        deleted = purge_old_prices(db)  # no explicit retention_days -> reads env
        assert deleted == 1

    def test_default_constant_is_one_week(self):
        assert DEFAULT_RETENTION_DAYS == 7
