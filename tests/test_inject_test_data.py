"""
Tests for inject_test_data.py — Story 6.2.

AC #2: inject mode creates FACT_ENERGY_FLOW rows that detect() picks up.
AC #3: restore mode removes injected data without touching real data.
"""

import os
import sqlite3
import tempfile

import pytest

from unittest.mock import patch

from scripts.inject_test_data import SENTINEL_TS, TEST_SOURCE, inject, main, restore
from shared.alerting.alert_detector import detect


# ── Schema helper (same structure as test_alert_detector.py) ──────────────────

_SCHEMA = """
    CREATE TABLE DIM_REGION (
        id_region INTEGER PRIMARY KEY AUTOINCREMENT,
        code_insee TEXT NOT NULL,
        nom_region TEXT
    );
    CREATE TABLE DIM_TIME (
        id_date INTEGER PRIMARY KEY AUTOINCREMENT,
        horodatage TEXT NOT NULL
    );
    CREATE TABLE DIM_SOURCE (
        id_source INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL
    );
    CREATE TABLE FACT_ENERGY_FLOW (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_region INTEGER NOT NULL,
        id_date INTEGER NOT NULL,
        id_source INTEGER NOT NULL,
        valeur_mw REAL,
        consommation_mw REAL
    );
"""


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _make_file_db():
    """Return a temp file path with the schema pre-created. Caller must delete."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _fact_count(conn):
    return conn.execute("SELECT COUNT(*) FROM FACT_ENERGY_FLOW").fetchone()[0]


def _sentinel_time_exists(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM DIM_TIME WHERE horodatage = ?", (SENTINEL_TS,)
    ).fetchone()[0] > 0


# ── inject ────────────────────────────────────────────────────────────────────

def test_inject_creates_fact_row():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    assert _fact_count(conn) == 1


def test_inject_fact_row_has_correct_values():
    conn = _make_db()
    inject(conn, "FR", "under_production", 3500.0, 5500.0)
    row = conn.execute("SELECT valeur_mw, consommation_mw FROM FACT_ENERGY_FLOW").fetchone()
    assert row == (3500.0, 5500.0)


def test_inject_under_production_detected_by_detector():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)

    alerts = detect(conn)

    assert len(alerts) == 1
    assert alerts[0]["region_code"] == "FR"
    assert alerts[0]["alert_type"] == "under_production"
    assert alerts[0]["prod_mw"] == 4000.0
    assert alerts[0]["conso_mw"] == 6000.0


def test_inject_over_production_detected_by_detector():
    conn = _make_db()
    inject(conn, "IDF", "over_production", 8000.0, 5000.0)

    alerts = detect(conn)

    assert len(alerts) == 1
    assert alerts[0]["region_code"] == "IDF"
    assert alerts[0]["alert_type"] == "over_production"


def test_inject_does_not_affect_other_regions():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)

    alerts = detect(conn)

    region_codes = [a["region_code"] for a in alerts]
    assert "IDF" not in region_codes
    assert "FR" in region_codes


def test_inject_creates_sentinel_dim_time_row():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    assert _sentinel_time_exists(conn)


def test_inject_creates_test_source_row():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    count = conn.execute(
        "SELECT COUNT(*) FROM DIM_SOURCE WHERE source_name = ?", (TEST_SOURCE,)
    ).fetchone()[0]
    assert count == 1


def test_inject_invalid_alert_type_raises():
    conn = _make_db()
    with pytest.raises(ValueError, match="Invalid alert_type"):
        inject(conn, "FR", "bad_type", 4000.0, 6000.0)


def test_inject_under_production_wrong_values_raises():
    conn = _make_db()
    with pytest.raises(ValueError, match="under_production requires prod_mw < conso_mw"):
        inject(conn, "FR", "under_production", 6000.0, 4000.0)  # prod > conso


def test_inject_over_production_wrong_values_raises():
    conn = _make_db()
    with pytest.raises(ValueError, match="over_production requires prod_mw > conso_mw"):
        inject(conn, "FR", "over_production", 4000.0, 6000.0)  # prod < conso


# ── restore ───────────────────────────────────────────────────────────────────

def test_restore_removes_injected_data():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    assert _fact_count(conn) == 1

    restore(conn)

    assert _fact_count(conn) == 0
    assert not _sentinel_time_exists(conn)


def test_restore_detect_returns_empty_after_restore():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    restore(conn)

    alerts = detect(conn)
    assert alerts == []


def test_restore_idempotent():
    conn = _make_db()
    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    restore(conn)
    restore(conn)  # second restore must not raise
    assert _fact_count(conn) == 0


def test_restore_on_empty_db_does_not_raise():
    conn = _make_db()
    restore(conn)  # nothing injected — should be a no-op


# ── main() CLI ────────────────────────────────────────────────────────────────

def test_main_inject_returns_0():
    db_path = _make_file_db()
    try:
        with patch("scripts.inject_test_data._get_connection",
                   side_effect=lambda: sqlite3.connect(db_path)):
            rc = main(["--mode", "inject", "--region", "FR", "--alert-type", "under_production"])
        assert rc == 0
        conn = sqlite3.connect(db_path)
        assert _fact_count(conn) == 1
        conn.close()
    finally:
        os.unlink(db_path)


def test_main_restore_returns_0():
    db_path = _make_file_db()
    try:
        with patch("scripts.inject_test_data._get_connection",
                   side_effect=lambda: sqlite3.connect(db_path)):
            main(["--mode", "inject", "--region", "FR", "--alert-type", "under_production"])
            rc = main(["--mode", "restore"])
        assert rc == 0
        conn = sqlite3.connect(db_path)
        assert _fact_count(conn) == 0
        conn.close()
    finally:
        os.unlink(db_path)


def test_main_defaults_prod_conso():
    """--prod-mw and --conso-mw have sensible defaults for each alert type."""
    db_path = _make_file_db()
    try:
        with patch("scripts.inject_test_data._get_connection",
                   side_effect=lambda: sqlite3.connect(db_path)):
            rc = main(["--mode", "inject", "--region", "FR", "--alert-type", "over_production"])
        assert rc == 0
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT valeur_mw, consommation_mw FROM FACT_ENERGY_FLOW").fetchone()
        conn.close()
        assert row[0] > row[1]  # over_production: prod > conso
    finally:
        os.unlink(db_path)


def test_main_returns_1_on_error():
    with patch("scripts.inject_test_data._get_connection", side_effect=RuntimeError("db down")):
        rc = main(["--mode", "inject", "--region", "FR", "--alert-type", "under_production"])
    assert rc == 1


def test_restore_does_not_remove_real_data():
    conn = _make_db()
    # Insert real (non-injected) data
    conn.execute("INSERT INTO DIM_REGION VALUES (1, 'FR', 'France')")
    conn.execute("INSERT INTO DIM_TIME VALUES (1, '2026-03-11T12:00:00')")
    conn.execute("INSERT INTO DIM_SOURCE VALUES (1, 'nucleaire')")
    conn.execute("INSERT INTO FACT_ENERGY_FLOW (id_region, id_date, id_source, valeur_mw, consommation_mw) VALUES (1, 1, 1, 5000.0, 4000.0)")
    conn.commit()

    inject(conn, "FR", "under_production", 4000.0, 6000.0)
    restore(conn)

    # Real row must still exist
    assert _fact_count(conn) == 1
    row = conn.execute("SELECT valeur_mw FROM FACT_ENERGY_FLOW").fetchone()
    assert row[0] == 5000.0
