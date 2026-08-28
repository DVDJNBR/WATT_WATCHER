"""Tests for silver_storage.py — FT/MEDALLION."""

from pathlib import Path

import pandas as pd
import pytest

from functions.shared.silver_storage import SilverStorage


@pytest.fixture
def local_storage(tmp_path):
    """SilverStorage in local mode with temp directory."""
    return SilverStorage(local_mode=True, local_root=str(tmp_path))


class TestWriteParquetLocal:
    def test_single_file_no_partitioning(self, local_storage, tmp_path):
        df = pd.DataFrame({"region_code": ["11"], "puissance_installee_mw": [123.4]})
        files = local_storage.write_parquet(df, source="capacity")
        assert files == 1
        out = tmp_path / "capacity" / "data.parquet"
        assert out.exists()
        assert pd.read_parquet(out).equals(df)

    def test_sub_path_included(self, local_storage, tmp_path):
        df = pd.DataFrame({"a": [1]})
        local_storage.write_parquet(df, source="meteo", sub_path="regional")
        assert (tmp_path / "meteo" / "regional" / "data.parquet").exists()

    def test_hive_partitioned(self, local_storage, tmp_path):
        df = pd.DataFrame({
            "value": [1, 2, 3],
            "year": [2026, 2026, 2025],
            "month": [8, 9, 12],
        })
        files = local_storage.write_parquet(df, source="price", sub_path="market", partition_cols=["year", "month"])
        assert files == 3
        assert (tmp_path / "price" / "market" / "year=2026" / "month=08" / "data.parquet").exists()
        assert (tmp_path / "price" / "market" / "year=2026" / "month=09" / "data.parquet").exists()
        assert (tmp_path / "price" / "market" / "year=2025" / "month=12" / "data.parquet").exists()

    def test_partition_columns_dropped_from_output(self, local_storage, tmp_path):
        df = pd.DataFrame({"value": [1], "year": [2026], "month": [8]})
        local_storage.write_parquet(df, source="x", partition_cols=["year", "month"])
        out = pd.read_parquet(tmp_path / "x" / "year=2026" / "month=08" / "data.parquet")
        assert list(out.columns) == ["value"]

    def test_empty_dataframe_writes_nothing(self, local_storage, tmp_path):
        files = local_storage.write_parquet(pd.DataFrame(), source="empty")
        assert files == 0
        assert not (tmp_path / "empty").exists()


class TestUploadDirectory:
    def test_noop_in_local_mode(self, local_storage, tmp_path):
        """upload_directory is only meaningful for the ADLS path (RTE's real
        Silver-persistence fix); local_mode files already live in place."""
        some_dir = tmp_path / "somewhere"
        some_dir.mkdir()
        (some_dir / "data.parquet").write_bytes(b"not a real parquet, doesn't matter")
        uploaded = local_storage.upload_directory(some_dir, prefix="rte/production")
        assert uploaded == 0
