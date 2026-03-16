"""Tests for Quality Gates — Story 3.3, Task 5"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from functions.shared.gold.dim_loader import DimLoader
from functions.shared.quality.checks import (  # type: ignore
    fk_integrity_check,
    freshness_check,
    null_check,
    range_check,
    row_count_check,
)
from functions.shared.quality.gate_runner import GateRunner  # type: ignore


CONFIG_PATH = Path("config/quality_gates.json")


# ─── Individual Checks ──────────────────────────────────────────────────────

class TestNullCheck:
    def test_pass_no_nulls(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        result = null_check(df, ["a", "b"])
        assert result["status"] == "PASS"

    def test_fail_with_nulls(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": ["x", "y", None]})
        result = null_check(df, ["a", "b"])
        assert result["status"] == "FAIL"
        assert result["details"]["nulls_found"]["a"] == 1

    def test_missing_column(self):
        df = pd.DataFrame({"a": [1, 2]})
        result = null_check(df, ["nonexistent"])
        assert result["status"] == "FAIL"


class TestRangeCheck:
    def test_pass_in_range(self):
        df = pd.DataFrame({"mw": [100.0, 5000.0, 50000.0]})
        result = range_check(df, "mw", 0, 100000)
        assert result["status"] == "PASS"

    def test_fail_out_of_range(self):
        df = pd.DataFrame({"mw": [100.0, -50.0, 200000.0]})
        result = range_check(df, "mw", 0, 100000)
        assert result["status"] == "FAIL"
        assert result["details"]["out_of_range_count"] == 2


class TestRowCountCheck:
    def test_pass_within_tolerance(self):
        result = row_count_check(actual=98, expected=100, tolerance_pct=5)
        assert result["status"] == "PASS"

    def test_fail_outside_tolerance(self):
        result = row_count_check(actual=50, expected=100, tolerance_pct=5)
        assert result["status"] == "FAIL"

    def test_warn_borderline(self):
        result = row_count_check(actual=90, expected=100, tolerance_pct=5)
        assert result["status"] == "WARN"


class TestFreshnessCheck:
    def test_pass_fresh_data(self):
        now = datetime.now(timezone.utc)
        df = pd.DataFrame({"ts": [now - timedelta(hours=2)]})
        result = freshness_check(df, "ts", max_age_hours=24, reference_time=now)
        assert result["status"] == "PASS"

    def test_fail_stale_data(self):
        now = datetime.now(timezone.utc)
        df = pd.DataFrame({"ts": [now - timedelta(days=5)]})
        result = freshness_check(df, "ts", max_age_hours=24, reference_time=now)
        assert result["status"] == "FAIL"


class TestFKIntegrity:
    def test_pass_valid_fks(self):
        conn = sqlite3.connect(":memory:")
        dim = DimLoader(conn)
        dim.ensure_schema()
        dim.upsert_sources()
        dim.upsert_regions([{"code_insee": "11", "nom_region": "IDF"}])
        dim.upsert_time(["2025-06-15T10:00:00+00:00"])

        # Insert a valid fact row
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO FACT_ENERGY_FLOW (id_date, id_region, id_source, valeur_mw) VALUES (1, 1, 1, 100)"
        )
        conn.commit()

        result = fk_integrity_check(conn, "FACT_ENERGY_FLOW", {
            "id_region": "DIM_REGION",
            "id_source": "DIM_SOURCE",
            "id_date": "DIM_TIME",
        })
        assert result["status"] == "PASS"

    def test_fail_orphan_fks(self):
        conn = sqlite3.connect(":memory:")
        dim = DimLoader(conn)
        dim.ensure_schema()

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO FACT_ENERGY_FLOW (id_date, id_region, id_source, valeur_mw) VALUES (999, 999, 999, 100)"
        )
        conn.commit()

        result = fk_integrity_check(conn, "FACT_ENERGY_FLOW", {
            "id_region": "DIM_REGION",
        })
        assert result["status"] == "FAIL"


# ─── Gate Runner Tests ───────────────────────────────────────────────────────

class TestGateRunner:
    def test_run_programmatic(self):
        """AC #1: Run checks programmatically."""
        df = pd.DataFrame({
            "code_insee_region": ["11", "84"],
            "date_heure": ["2025-06-15", "2025-06-15"],
            "consommation_mw": [8500.0, 5200.0],
        })

        runner = GateRunner()
        results = runner.run_checks([
            {"name": "null_test", "check": "null_check",
             "columns": ["code_insee_region", "date_heure"],
             "severity": "CRITICAL"},
            {"name": "range_test", "check": "range_check",
             "column": "consommation_mw", "min": 0, "max": 100000,
             "severity": "WARNING"},
        ], context={"df": df})

        assert len(results) == 2
        assert all(r["status"] == "PASS" for r in results)

    def test_summary(self):
        """Summary correctly counts pass/fail/warn."""
        runner = GateRunner()
        runner.results = [
            {"status": "PASS", "severity": "INFO"},
            {"status": "FAIL", "severity": "CRITICAL"},
            {"status": "WARN", "severity": "WARNING"},
        ]
        summary = runner.get_summary()
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["warned"] == 1
        assert summary["pipeline_should_halt"] is True

    def test_config_driven(self):
        """AC #3: Config-driven gate execution."""
        if not CONFIG_PATH.exists():
            pytest.skip("Config not found")

        df = pd.DataFrame({
            "code_insee_region": ["11"],
            "date_heure": [datetime.now(timezone.utc)],
            "consommation_mw": [8500.0],
        })

        runner = GateRunner()
        results = runner.run_from_config(
            CONFIG_PATH,
            context={"rte_production": df, "df": df},
        )
        # At minimum the Silver checks should run
        assert len(results) > 0
