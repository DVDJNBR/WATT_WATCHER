"""
Tests for alert_detector.py — Story 5.2.

AC #3: Détecte under_production (prod < conso) et over_production (prod > conso).
AC #4: Retourne {region_code, alert_type, prod_mw, conso_mw}.
AC #5: Skip si consommation NULL ou <= 0.
AC #6: Tests avec SQLite in-memory.
"""

import sqlite3

from shared.alerting.alert_detector import detect


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE DIM_REGION (
            id_region INTEGER PRIMARY KEY,
            code_insee TEXT NOT NULL,
            nom_region TEXT
        );
        CREATE TABLE DIM_TIME (
            id_date INTEGER PRIMARY KEY,
            horodatage TEXT NOT NULL
        );
        CREATE TABLE DIM_SOURCE (
            id_source INTEGER PRIMARY KEY,
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
    """)
    conn.execute("INSERT INTO DIM_SOURCE VALUES (1, 'nucleaire')")
    conn.execute("INSERT INTO DIM_SOURCE VALUES (2, 'eolien')")
    conn.execute("INSERT INTO DIM_TIME VALUES (1, '2026-03-11T12:00:00')")
    conn.commit()
    return conn


def _add_region(conn, id_region, code_insee):
    conn.execute("INSERT INTO DIM_REGION VALUES (?, ?, ?)", (id_region, code_insee, code_insee))
    conn.commit()


def _add_fact(conn, id_region, id_source, valeur_mw, consommation_mw, id_date=1):
    conn.execute(
        "INSERT INTO FACT_ENERGY_FLOW (id_region, id_date, id_source, valeur_mw, consommation_mw) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_region, id_date, id_source, valeur_mw, consommation_mw),
    )
    conn.commit()


# ── Basic detection tests ─────────────────────────────────────────────────────

def test_empty_table_returns_empty_list():
    conn = _make_db()
    result = detect(conn)
    assert result == []


def test_under_production_detected():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 4000.0, 6000.0)  # prod < conso
    result = detect(conn)
    assert len(result) == 1
    assert result[0]["region_code"] == "FR"
    assert result[0]["alert_type"] == "under_production"
    assert result[0]["prod_mw"] == 4000.0
    assert result[0]["conso_mw"] == 6000.0


def test_over_production_detected():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 8000.0, 6000.0)  # prod > conso
    result = detect(conn)
    assert len(result) == 1
    assert result[0]["region_code"] == "FR"
    assert result[0]["alert_type"] == "over_production"
    assert result[0]["prod_mw"] == 8000.0
    assert result[0]["conso_mw"] == 6000.0


def test_balanced_region_no_alert():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 6000.0, 6000.0)  # prod == conso
    result = detect(conn)
    assert result == []


# ── NULL / zero consumption tests ─────────────────────────────────────────────

def test_null_consumption_skipped():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 5000.0, None)
    result = detect(conn)
    assert result == []


def test_zero_consumption_skipped():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 5000.0, 0.0)
    result = detect(conn)
    assert result == []


# ── Multi-source summing ──────────────────────────────────────────────────────

def test_production_summed_across_sources():
    """SUM(valeur_mw) across multiple sources for same region."""
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 2000.0, 6000.0)  # nucleaire
    _add_fact(conn, 1, 2, 2000.0, 6000.0)  # eolien
    # total prod = 4000 < 6000 → under_production
    result = detect(conn)
    assert len(result) == 1
    assert result[0]["alert_type"] == "under_production"
    assert result[0]["prod_mw"] == 4000.0


def test_multi_source_over_production():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 4000.0, 6000.0)
    _add_fact(conn, 1, 2, 4000.0, 6000.0)
    # total prod = 8000 > 6000 → over_production
    result = detect(conn)
    assert len(result) == 1
    assert result[0]["alert_type"] == "over_production"
    assert result[0]["prod_mw"] == 8000.0


# ── Multiple regions ──────────────────────────────────────────────────────────

def test_multiple_regions_correct_alerts():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_region(conn, 2, "BE")
    _add_region(conn, 3, "DE")
    _add_fact(conn, 1, 1, 4000.0, 6000.0)   # FR: under
    _add_fact(conn, 2, 1, 8000.0, 6000.0)   # BE: over
    _add_fact(conn, 3, 1, 6000.0, 6000.0)   # DE: balanced
    result = detect(conn)
    assert len(result) == 2
    types = {r["region_code"]: r["alert_type"] for r in result}
    assert types["FR"] == "under_production"
    assert types["BE"] == "over_production"
    assert "DE" not in types


def test_only_latest_timestamp_used():
    """Detector uses MAX(horodatage) — old data must not generate alerts."""
    conn = _make_db()
    conn.execute("INSERT INTO DIM_TIME VALUES (2, '2026-03-11T13:00:00')")  # newer
    conn.commit()
    _add_region(conn, 1, "FR")
    # Old timestamp: imbalanced
    _add_fact(conn, 1, 1, 4000.0, 6000.0, id_date=1)
    # New timestamp: balanced
    _add_fact(conn, 1, 1, 6000.0, 6000.0, id_date=2)
    result = detect(conn)
    # Only new timestamp used → balanced → no alert
    assert result == []


def test_return_dict_has_correct_keys():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 4000.0, 6000.0)
    result = detect(conn)
    assert len(result) == 1
    assert set(result[0].keys()) == {"region_code", "alert_type", "prod_mw", "conso_mw"}


def test_prod_mw_and_conso_mw_are_floats():
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, 4000, 6000)  # integers in DB
    result = detect(conn)
    assert isinstance(result[0]["prod_mw"], float)
    assert isinstance(result[0]["conso_mw"], float)


def test_null_prod_mw_skipped():
    """SUM(valeur_mw) = NULL if all valeur_mw are NULL → region skipped."""
    conn = _make_db()
    _add_region(conn, 1, "FR")
    _add_fact(conn, 1, 1, None, 6000.0)  # valeur_mw NULL
    result = detect(conn)
    assert result == []
