"""Tests for Alert Engine & Alert Store — Story 5.2, Task 4"""

import json
import os
from pathlib import Path

import polars as pl
import pytest

from functions.shared.alerting.alert_engine import evaluate, _get_threshold, LOW_DEMAND_HOURS
from functions.shared.alerting.alert_store import AlertStore


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_silver(tmp_path: Path, ratio: float, hour: int = 12) -> Path:
    """Create a minimal Silver Parquet with given production/consumption ratio."""
    from datetime import datetime, timezone
    ts = datetime(2025, 6, 15, hour, 0, 0, tzinfo=timezone.utc).isoformat()
    production = ratio * 5000.0   # consumption fixed at 5000 MW
    df = pl.DataFrame({
        "code_insee_region": ["11"],
        "libelle_region": ["Île-de-France"],
        "date_heure": [ts],
        "nucleaire_mw": [production * 0.6],
        "eolien_mw": [production * 0.2],
        "solaire_mw": [production * 0.1],
        "hydraulique_mw": [production * 0.05],
        "gaz_mw": [production * 0.05],
        "charbon_mw": [0.0],
        "fioul_mw": [0.0],
        "bioenergies_mw": [0.0],
        "consommation_mw": [5000.0],
        "temperature_c": [18.5],
    })
    path = tmp_path / "silver.parquet"
    df.write_parquet(path)
    return path


# ─── AlertEngine Tests ────────────────────────────────────────────────────────

class TestAlertEngine:
    def test_no_alert_below_threshold(self, tmp_path):
        """AC #1, #3: No alert when ratio < threshold."""
        path = _make_silver(tmp_path, ratio=0.95)
        alerts = evaluate(path)
        assert alerts == []

    def test_overproduction_critical(self, tmp_path):
        """AC #1: CRITICAL alert when production > 110% of consumption."""
        path = _make_silver(tmp_path, ratio=1.15, hour=12)
        alerts = evaluate(path)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "OVERPRODUCTION"
        assert alerts[0]["severity"] == "CRITICAL"
        assert alerts[0]["region"] == "11"
        assert alerts[0]["ratio"] > 1.10

    def test_negative_price_risk_warning(self, tmp_path):
        """AC #4: WARNING when ratio > neg-price threshold during low-demand hours."""
        # ratio=1.07 (above 1.05, below 1.10) at hour=3 (low demand)
        path = _make_silver(tmp_path, ratio=1.07, hour=3)
        alerts = evaluate(path)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "NEGATIVE_PRICE_RISK"
        assert alerts[0]["severity"] == "WARNING"

    def test_no_neg_price_during_peak_hours(self, tmp_path):
        """AC #4: No negative price warning during peak hours (9-21h)."""
        path = _make_silver(tmp_path, ratio=1.07, hour=14)
        alerts = evaluate(path)
        assert alerts == []

    def test_overproduction_beats_neg_price(self, tmp_path):
        """AC #1: CRITICAL overproduction takes priority (not double-counted)."""
        path = _make_silver(tmp_path, ratio=1.20, hour=3)
        alerts = evaluate(path)
        # Only OVERPRODUCTION (ratio > 1.10), not also NEGATIVE_PRICE_RISK
        types = [a["type"] for a in alerts]
        assert "OVERPRODUCTION" in types
        assert "NEGATIVE_PRICE_RISK" not in types

    def test_alert_has_required_fields(self, tmp_path):
        """AC #2: Alert dict contains all required fields."""
        path = _make_silver(tmp_path, ratio=1.15)
        alerts = evaluate(path)
        required = {"alert_id", "type", "severity", "region", "timestamp", "details", "ratio", "acknowledged"}
        assert required.issubset(alerts[0].keys())

    def test_configurable_threshold_env(self, tmp_path, monkeypatch):
        """AC #3: Threshold configurable via OVERPRODUCTION_THRESHOLD env var."""
        monkeypatch.setenv("OVERPRODUCTION_THRESHOLD", "1.30")
        path = _make_silver(tmp_path, ratio=1.15)  # above 1.10 but below 1.30
        alerts = evaluate(path)
        assert alerts == []

    def test_empty_silver_returns_no_alerts(self, tmp_path):
        """AC #1: Empty directory → no alerts (no crash)."""
        alerts = evaluate(tmp_path)
        assert alerts == []

    def test_missing_consommation_col(self, tmp_path):
        """Alert engine is safe when consommation_mw is missing."""
        df = pl.DataFrame({"date_heure": ["2025-06-15T10:00:00+00:00"], "nucleaire_mw": [3000.0]})
        path = tmp_path / "s.parquet"
        df.write_parquet(path)
        alerts = evaluate(path)
        assert alerts == []

    def test_low_demand_hours_set(self):
        """AC #4: LOW_DEMAND_HOURS covers 00-07 and 22-23."""
        assert 0 in LOW_DEMAND_HOURS
        assert 7 in LOW_DEMAND_HOURS
        assert 8 not in LOW_DEMAND_HOURS
        assert 22 in LOW_DEMAND_HOURS
        assert 23 in LOW_DEMAND_HOURS

    def test_threshold_helper_default(self, monkeypatch):
        """AC #3: _get_threshold returns default when env var not set."""
        monkeypatch.delenv("OVERPRODUCTION_THRESHOLD", raising=False)
        assert _get_threshold("OVERPRODUCTION_THRESHOLD", 1.10) == 1.10

    def test_threshold_helper_invalid_falls_back(self, monkeypatch):
        """AC #3: Invalid env var → falls back to default."""
        monkeypatch.setenv("OVERPRODUCTION_THRESHOLD", "not_a_number")
        assert _get_threshold("OVERPRODUCTION_THRESHOLD", 1.10) == 1.10


# ─── AlertStore Tests ─────────────────────────────────────────────────────────

class TestAlertStore:
    def _sample_alert(self, alert_id="abc123", severity="CRITICAL", region="11", ack=False):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "alert_id": alert_id,
            "type": "OVERPRODUCTION",
            "severity": severity,
            "region": region,
            "region_label": "Île-de-France",
            "timestamp": ts,
            "data_timestamp": ts,
            "details": "Test",
            "ratio": 1.15,
            "acknowledged": ack,
        }

    def test_save_and_read(self, tmp_path):
        """AC #2: Alert is saved and readable."""
        store = AlertStore(base_path=tmp_path)
        alert = self._sample_alert()
        count = store.save([alert])
        assert count == 1
        results = store.read_recent(days=30)
        assert len(results) == 1
        assert results[0]["alert_id"] == "abc123"

    def test_empty_store_returns_empty(self, tmp_path):
        """No alerts → empty list."""
        store = AlertStore(base_path=tmp_path)
        assert store.read_recent() == []

    def test_filter_by_region(self, tmp_path):
        """Filter by region returns only matching alerts."""
        store = AlertStore(base_path=tmp_path)
        store.save([
            self._sample_alert(alert_id="a1", region="11"),
            self._sample_alert(alert_id="a2", region="84"),
        ])
        results = store.read_recent(region="11")
        assert all(r["region"] == "11" for r in results)
        assert len(results) == 1

    def test_filter_active_status(self, tmp_path):
        """status='active' excludes acknowledged alerts."""
        store = AlertStore(base_path=tmp_path)
        store.save([
            self._sample_alert(alert_id="active1", ack=False),
            self._sample_alert(alert_id="acked1", ack=True),
        ])
        results = store.read_recent(status="active")
        assert all(not r["acknowledged"] for r in results)

    def test_filter_acknowledged_status(self, tmp_path):
        """status='acknowledged' returns only acknowledged alerts."""
        store = AlertStore(base_path=tmp_path)
        store.save([
            self._sample_alert(alert_id="active1", ack=False),
            self._sample_alert(alert_id="acked1", ack=True),
        ])
        results = store.read_recent(status="acknowledged")
        assert all(r["acknowledged"] for r in results)

    def test_save_empty_list(self, tmp_path):
        """Saving empty list does nothing."""
        store = AlertStore(base_path=tmp_path)
        assert store.save([]) == 0

    def test_file_written_as_json(self, tmp_path):
        """Alert is persisted as valid JSON."""
        store = AlertStore(base_path=tmp_path)
        alert = self._sample_alert(alert_id="json_test")
        store.save([alert])
        files = list((tmp_path / "audit" / "alerts").rglob("*.json"))
        assert len(files) == 1
        loaded = json.loads(files[0].read_text())
        assert loaded["alert_id"] == "json_test"
