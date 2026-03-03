"""Tests for Silver transformation modules — Story 3.1, Task 7"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from functions.shared.transformations.data_quality import (
    NullStrategy,
    apply_quality_rules,
)
from functions.shared.transformations.rte_silver import transform_rte_to_silver
from functions.shared.transformations.capacity_silver import transform_capacity_to_silver
from functions.shared.transformations.maintenance_silver import transform_maintenance_to_silver
from functions.shared.transformations.era5_silver import transform_era5_to_silver


FIXTURE_DIR = Path("tests/fixtures")


# ─── Data Quality Tests ─────────────────────────────────────────────────────

class TestDataQuality:
    def test_fill_zero(self):
        df = pd.DataFrame({"val": [1.0, None, 3.0]})
        rules = {"val": NullStrategy.FILL_ZERO}
        result, metrics = apply_quality_rules(df, rules, "test")
        assert result["val"].tolist() == [1.0, 0.0, 3.0]
        assert metrics["values_filled"] == 1

    def test_drop_rows(self):
        df = pd.DataFrame({"key": ["a", None, "c"], "val": [1, 2, 3]})
        rules = {"key": NullStrategy.DROP}
        result, metrics = apply_quality_rules(df, rules, "test")
        assert len(result) == 2
        assert metrics["rows_dropped"] == 1

    def test_flag_nulls(self):
        df = pd.DataFrame({"val": [1.0, None, 3.0]})
        rules = {"val": NullStrategy.FLAG}
        result, metrics = apply_quality_rules(df, rules, "test")
        assert "val_is_null" in result.columns
        assert result["val_is_null"].tolist() == [False, True, False]
        assert metrics["values_flagged"] == 1

    def test_forward_fill(self):
        df = pd.DataFrame({"val": [10.0, None, None, 20.0]})
        rules = {"val": NullStrategy.FORWARD_FILL}
        result, _ = apply_quality_rules(df, rules, "test")
        assert result["val"].tolist() == [10.0, 10.0, 10.0, 20.0]

    def test_quality_metrics(self):
        df = pd.DataFrame({"a": [1, None], "b": [None, 2]})
        rules = {"a": NullStrategy.DROP, "b": NullStrategy.FILL_ZERO}
        _, metrics = apply_quality_rules(df, rules, "test")
        assert metrics["input_rows"] == 2
        assert metrics["source"] == "test"


# ─── RTE Silver Tests ───────────────────────────────────────────────────────

class TestRTESilver:
    @pytest.fixture
    def bronze_json(self, tmp_path):
        records = [
            {
                "code_insee_region": "11",
                "libelle_region": "Île-de-France",
                "date_heure": "2025-06-15T10:00:00+02:00",
                "consommation": 8500,
                "nucleaire": 3200,
                "eolien": 450.0,
                "solaire": 320,
                "hydraulique": 180,
                "gaz": 120,
                "charbon": 0,
                "fioul": 0,
                "bioenergies": 45,
                "pompage": "0",  # String type issue from Story 0.1
            },
            {
                "code_insee_region": "11",
                "libelle_region": "Île-de-France",
                "date_heure": "2025-06-15T10:00:00+02:00",  # Duplicate!
                "consommation": 8500,
                "nucleaire": 3200,
                "eolien": 450.0,
                "solaire": 320,
                "hydraulique": 180,
                "gaz": 120,
                "charbon": 0,
                "fioul": 0,
                "bioenergies": 45,
                "pompage": "0",
            },
            {
                "code_insee_region": "84",
                "libelle_region": "Auvergne-Rhône-Alpes",
                "date_heure": "2025-06-15T10:00:00+02:00",
                "consommation": 5200,
                "nucleaire": 2100,
                "eolien": 280,
                "solaire": 510,
                "hydraulique": 890,
                "gaz": 0,
                "charbon": 0,
                "fioul": 0,
                "bioenergies": 30,
                "pompage": 0,
            },
        ]
        f = tmp_path / "bronze.json"
        f.write_text(json.dumps(records), encoding="utf-8")
        return f

    def test_rte_transform(self, bronze_json, tmp_path):
        result = transform_rte_to_silver(bronze_json, tmp_path)
        assert result["status"] == "success"
        assert result["output_rows"] == 2  # 1 dupe removed

    def test_deduplication(self, bronze_json, tmp_path):
        result = transform_rte_to_silver(bronze_json, tmp_path)
        assert result["duplicates_removed"] == 1

    def test_column_rename(self, bronze_json, tmp_path):
        transform_rte_to_silver(bronze_json, tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(parquets[0])
        assert "consommation_mw" in df.columns
        assert "nucleaire_mw" in df.columns

    def test_pompage_cast(self, bronze_json, tmp_path):
        """Story 0.1 bug: pompage is sometimes str."""
        transform_rte_to_silver(bronze_json, tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(parquets[0])
        assert pd.api.types.is_float_dtype(df["pompage_mw"])

    def test_hive_partitioning(self, bronze_json, tmp_path):
        transform_rte_to_silver(bronze_json, tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        assert any("year=" in str(p) for p in parquets)


# ─── Capacity Silver Tests ──────────────────────────────────────────────────

class TestCapacitySilver:
    def test_capacity_transform(self, tmp_path):
        result = transform_capacity_to_silver(
            FIXTURE_DIR / "capacity_sample.csv", tmp_path
        )
        assert result["status"] == "success"
        assert result["output_rows"] > 0

    def test_parquet_output(self, tmp_path):
        transform_capacity_to_silver(FIXTURE_DIR / "capacity_sample.csv", tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        assert len(parquets) == 1


# ─── Maintenance Silver Tests ───────────────────────────────────────────────

class TestMaintenanceSilver:
    @pytest.fixture
    def maintenance_json(self, tmp_path):
        events = [
            {"event_id": "EVT-001", "start_date": "2026-03-01T06:00:00Z",
             "end_date": "2026-04-15T18:00:00Z", "description": "Visite  décennale",
             "affected_area": "Hauts-de-France", "unit_name": "GRAVELINES 5"},
            {"event_id": "EVT-001", "start_date": "2026-03-01T06:00:00Z",
             "end_date": "2026-04-15T18:00:00Z", "description": "Visite  décennale",
             "affected_area": "Hauts-de-France", "unit_name": "GRAVELINES 5"},  # Dupe
            {"event_id": "EVT-002", "start_date": "2026-02-20T14:30:00Z",
             "end_date": "2026-02-28T23:59:00Z", "description": "Arrêt pompe",
             "affected_area": "Grand Est", "unit_name": "CATTENOM 3"},
        ]
        f = tmp_path / "maintenance.json"
        f.write_text(json.dumps(events), encoding="utf-8")
        return f

    def test_maintenance_transform(self, maintenance_json, tmp_path):
        result = transform_maintenance_to_silver(maintenance_json, tmp_path)
        assert result["status"] == "success"
        assert result["output_rows"] == 2  # 1 dupe removed

    def test_description_cleaned(self, maintenance_json, tmp_path):
        transform_maintenance_to_silver(maintenance_json, tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(parquets[0])
        for desc in df["description"].tolist():
            assert "  " not in desc  # No double spaces


# ─── ERA5 Silver Tests ──────────────────────────────────────────────────────

class TestERA5Silver:
    def test_era5_transform(self, tmp_path):
        result = transform_era5_to_silver(
            FIXTURE_DIR / "era5_sample.parquet", tmp_path
        )
        assert result["status"] == "success"
        assert result["output_rows"] > 0

    def test_hive_partitioned(self, tmp_path):
        transform_era5_to_silver(FIXTURE_DIR / "era5_sample.parquet", tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        assert any("year=" in str(p) for p in parquets)

    def test_derived_fields(self, tmp_path):
        transform_era5_to_silver(FIXTURE_DIR / "era5_sample.parquet", tmp_path)
        parquets = list(tmp_path.rglob("*.parquet"))
        df = pd.read_parquet(parquets[0])
        assert "wind_speed_100m" in df.columns
        assert "temperature_c" in df.columns
