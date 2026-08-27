"""Tests for transformations/price_silver.py — FT/PRICES."""

from datetime import datetime, timezone

from functions.shared.transformations.price_silver import transform_price_to_silver


class TestTransformPriceToSilver:
    def test_empty_input(self):
        df = transform_price_to_silver([])
        assert df.empty

    def test_basic_normalization(self):
        records = [
            {"timestamp": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc), "price_eur_mwh": 45.0},
            {"timestamp": datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc), "price_eur_mwh": -3.2},
        ]
        df = transform_price_to_silver(records)
        assert len(df) == 2
        assert list(df.columns) == ["timestamp", "price_eur_mwh"]
        assert df.iloc[1]["price_eur_mwh"] == -3.2

    def test_drops_null_price(self):
        records = [
            {"timestamp": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc), "price_eur_mwh": 45.0},
            {"timestamp": datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc), "price_eur_mwh": None},
        ]
        df = transform_price_to_silver(records)
        assert len(df) == 1

    def test_dedup_keeps_last(self):
        """Overlapping fetch windows can return the same slot twice — keep the latest value."""
        ts = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        records = [
            {"timestamp": ts, "price_eur_mwh": 10.0},
            {"timestamp": ts, "price_eur_mwh": 12.0},
        ]
        df = transform_price_to_silver(records)
        assert len(df) == 1
        assert df.iloc[0]["price_eur_mwh"] == 12.0

    def test_sorted_by_timestamp(self):
        records = [
            {"timestamp": datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc), "price_eur_mwh": 1.0},
            {"timestamp": datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc), "price_eur_mwh": 2.0},
        ]
        df = transform_price_to_silver(records)
        assert df.iloc[0]["price_eur_mwh"] == 2.0
        assert df.iloc[1]["price_eur_mwh"] == 1.0
