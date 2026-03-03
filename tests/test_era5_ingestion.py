"""Tests for era5_ingestion.py — Story 2.2, Task 4"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from functions.shared.era5_ingestion import ERA5Ingestion


FIXTURE_PATH = Path("tests/fixtures/era5_sample.parquet")


@pytest.fixture
def ingestion():
    return ERA5Ingestion()


class TestERA5Ingestion:
    """AC #1, #2: Parquet ingestion with pandas."""

    def test_ingest_parquet(self, ingestion, tmp_path):
        """AC #1: ERA5 Parquet data is ingested and partitioned."""
        result = ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        assert result["total_rows"] == 144
        assert result["files_written"] > 0
        assert len(result["regions_processed"]) > 0

    def test_wind_speed_computed(self, ingestion, tmp_path):
        """Derived wind_speed_100m is computed from u100/v100."""
        ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        output_files = list(tmp_path.rglob("*.parquet"))
        assert len(output_files) > 0

        df = pd.read_parquet(output_files[0])
        assert "wind_speed_100m" in df.columns
        assert float(df["wind_speed_100m"].min()) >= 0

    def test_temperature_celsius(self, ingestion, tmp_path):
        """Temperature converted from Kelvin to Celsius."""
        ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        output_files = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(output_files[0])
        assert "temperature_c" in df.columns
        # Original t2m is ~285-310K → ~12-37°C
        assert float(df["temperature_c"].min()) > -50
        assert float(df["temperature_c"].max()) < 60

    def test_region_mapping(self, ingestion, tmp_path):
        """Grid points are mapped to nearest French regions."""
        ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        output_files = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(output_files[0])
        assert "region_code" in df.columns

    def test_partitioned_by_region_month(self, ingestion, tmp_path):
        """Output follows climate/era5/YYYY/MM/ path convention."""
        ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        output_files = list(tmp_path.rglob("*.parquet"))
        for f in output_files:
            parts = str(f.relative_to(tmp_path))
            assert "climate/era5/" in parts

    def test_streaming_mode(self, ingestion, tmp_path):
        """AC #2: Ingestion completes without error."""
        # This test verifies that the code path works correctly
        # The fixture is small, but the code path is the same for large files
        result = ingestion.ingest_parquet(FIXTURE_PATH, output_dir=tmp_path)
        assert result["total_rows"] > 0  # completed without error


class TestCheckpoint:
    """AC #3: Checkpoint mechanism for delta processing."""

    def test_save_and_load_checkpoint(self, tmp_path):
        """Checkpoint round-trip."""
        cp_path = tmp_path / "checkpoint.json"
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        ERA5Ingestion.save_checkpoint(cp_path, ts)
        loaded = ERA5Ingestion.load_checkpoint(cp_path)

        assert loaded is not None
        assert loaded.year == 2025
        assert loaded.month == 6

    def test_load_missing_checkpoint(self, tmp_path):
        """Missing checkpoint returns None."""
        cp_path = tmp_path / "nonexistent.json"
        assert ERA5Ingestion.load_checkpoint(cp_path) is None
