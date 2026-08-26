"""
Tests for alert_dispatcher.py — Story 5.3.

AC #2: Séquence detect → abonnés → dédup → send_alert → ALERT_SENT_LOG.
AC #3: Déduplication : 1 email/user/region/type/jour.
AC #4: Échec email → ALERT_SENT_LOG non inséré.
AC #5: Logs détection, envoi, skip.
AC #7: Cas : envoi normal, dédup, échec email, pas d'abonnés, plusieurs abonnés.
"""

import sqlite3
from unittest.mock import MagicMock

from shared.alerting.alert_dispatcher import dispatch_alerts


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE ALERT_SUBSCRIPTION (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE ALERT_SENT_LOG (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
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
    conn.execute("INSERT INTO DIM_TIME VALUES (1, '2026-03-11T12:00:00')")
    conn.commit()
    return conn


def _add_gold_data(conn, code_insee, prod_mw, conso_mw, id_region=1):
    conn.execute("INSERT OR IGNORE INTO DIM_REGION VALUES (?, ?, ?)", (id_region, code_insee, code_insee))
    conn.execute(
        "INSERT INTO FACT_ENERGY_FLOW (id_region, id_date, id_source, valeur_mw, consommation_mw) "
        "VALUES (?, 1, 1, ?, ?)",
        (id_region, prod_mw, conso_mw),
    )
    conn.commit()


def _add_user(conn, user_id, email):
    conn.execute("INSERT INTO USER_ACCOUNT (id, email) VALUES (?, ?)", (user_id, email))
    conn.commit()


def _add_subscription(conn, user_id, region_code, alert_type):
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type) VALUES (?, ?, ?)",
        (user_id, region_code, alert_type),
    )
    conn.commit()


def _count_sent_log(conn):
    return conn.execute("SELECT COUNT(*) FROM ALERT_SENT_LOG").fetchone()[0]


# ── Normal send ───────────────────────────────────────────────────────────────

def test_normal_send():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)   # under_production
    _add_user(conn, 1, "user@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    mock_svc.send_alert.assert_called_once_with(
        "user@test.com", "FR", "under_production", 4000.0, 6000.0
    )
    assert result["sent"] == 1
    assert result["skipped_dedup"] == 0
    assert result["errors"] == 0
    assert _count_sent_log(conn) == 1


def test_sent_log_row_inserted():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    dispatch_alerts(conn, MagicMock())

    row = conn.execute("SELECT user_id, region_code, alert_type FROM ALERT_SENT_LOG").fetchone()
    assert row == (1, "FR", "under_production")


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_dedup_skip_already_sent_today():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    # Pre-insert today's log
    conn.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) "
        "VALUES (1, 'FR', 'under_production', datetime('now'))"
    )
    conn.commit()
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    mock_svc.send_alert.assert_not_called()
    assert result["sent"] == 0
    assert result["skipped_dedup"] == 1


def test_dedup_does_not_block_different_user():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user1@test.com")
    _add_user(conn, 2, "user2@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    _add_subscription(conn, 2, "FR", "under_production")
    # Only user1 already sent
    conn.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) "
        "VALUES (1, 'FR', 'under_production', datetime('now'))"
    )
    conn.commit()
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    assert result["sent"] == 1
    assert result["skipped_dedup"] == 1
    mock_svc.send_alert.assert_called_once_with(
        "user2@test.com", "FR", "under_production", 4000.0, 6000.0
    )


# ── Email failure ─────────────────────────────────────────────────────────────

def test_email_failure_no_log_inserted():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    mock_svc = MagicMock()
    mock_svc.send_alert.side_effect = RuntimeError("Resend API down")

    result = dispatch_alerts(conn, mock_svc)

    assert result["errors"] == 1
    assert result["sent"] == 0
    assert _count_sent_log(conn) == 0  # No log inserted → retry next cycle


# ── No subscribers ────────────────────────────────────────────────────────────

def test_no_subscribers_no_email():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    # No subscription inserted
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    mock_svc.send_alert.assert_not_called()
    assert result["sent"] == 0
    assert result["detected"] == 1


def test_subscriber_inactive_not_notified():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user@test.com")
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) "
        "VALUES (1, 'FR', 'under_production', 0)"  # inactive
    )
    conn.commit()
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    mock_svc.send_alert.assert_not_called()
    assert result["sent"] == 0


# ── Multiple subscribers ──────────────────────────────────────────────────────

def test_multiple_subscribers_all_notified():
    conn = _make_db()
    _add_gold_data(conn, "FR", 4000.0, 6000.0)
    _add_user(conn, 1, "user1@test.com")
    _add_user(conn, 2, "user2@test.com")
    _add_user(conn, 3, "user3@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    _add_subscription(conn, 2, "FR", "under_production")
    _add_subscription(conn, 3, "FR", "under_production")
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    assert mock_svc.send_alert.call_count == 3
    assert result["sent"] == 3
    assert _count_sent_log(conn) == 3


# ── over_production alert type ────────────────────────────────────────────────

def test_over_production_alert_dispatched():
    conn = _make_db()
    _add_gold_data(conn, "FR", 8000.0, 5000.0)   # over_production
    _add_user(conn, 1, "user@test.com")
    _add_subscription(conn, 1, "FR", "over_production")
    mock_svc = MagicMock()

    result = dispatch_alerts(conn, mock_svc)

    mock_svc.send_alert.assert_called_once_with(
        "user@test.com", "FR", "over_production", 8000.0, 5000.0
    )
    assert result["sent"] == 1
    assert _count_sent_log(conn) == 1


# ── Counter accuracy ──────────────────────────────────────────────────────────

def test_return_counters_correct():
    conn = _make_db()
    # FR: under_production — user1 sent, user2 dedup, user3 error
    _add_gold_data(conn, "FR", 4000.0, 6000.0, id_region=1)
    _add_user(conn, 1, "u1@test.com")
    _add_user(conn, 2, "u2@test.com")
    _add_user(conn, 3, "u3@test.com")
    _add_subscription(conn, 1, "FR", "under_production")
    _add_subscription(conn, 2, "FR", "under_production")
    _add_subscription(conn, 3, "FR", "under_production")
    # user2 already sent today
    conn.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) "
        "VALUES (2, 'FR', 'under_production', datetime('now'))"
    )
    conn.commit()

    call_count = 0

    def side_effect(email, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if email == "u3@test.com":
            raise RuntimeError("fail")

    mock_svc = MagicMock()
    mock_svc.send_alert.side_effect = side_effect

    result = dispatch_alerts(conn, mock_svc)

    assert result["detected"] == 1
    assert result["sent"] == 1
    assert result["skipped_dedup"] == 1
    assert result["errors"] == 1
