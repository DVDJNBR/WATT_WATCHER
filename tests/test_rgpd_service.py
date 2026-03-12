"""
Tests for rgpd_service.py — Story 6.1.

AC #2: 11-month inactive accounts → warning email + inactivity_warning_sent_at set.
AC #3: 12-month inactive accounts → deleted (cascade).
AC #4: Each deletion is logged.
AC #6: warning sent, warning dedup, deletion, no-op, cascade, counters.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from shared.alerting.rgpd_service import _subtract_months, run_rgpd_cleanup


# ── Date helpers (relative to now — never hardcoded) ──────────────────────────

def _months_ago(n: int) -> str:
    """Return an ISO date string exactly N months before today (UTC)."""
    return _subtract_months(datetime.now(timezone.utc), n).strftime("%Y-%m-%d")


def _in_warning_window() -> str:
    """A date safely inside the 11-12 month warning window (11m + 15 days)."""
    base = _subtract_months(datetime.now(timezone.utc), 11)
    return (base - timedelta(days=15)).strftime("%Y-%m-%d")


def _recent() -> str:
    """A date 5 days ago — clearly active, no action needed."""
    return (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")


# ── Schema helper ─────────────────────────────────────────────────────────────

def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 1,
            last_activity TEXT NOT NULL,
            inactivity_warning_sent_at TEXT NULL
        );
        CREATE TABLE ALERT_SUBSCRIPTION (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


def _add_user(conn, user_id, email, last_activity, warning_sent_at=None):
    conn.execute(
        "INSERT INTO USER_ACCOUNT (id, email, last_activity, inactivity_warning_sent_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id, email, last_activity, warning_sent_at),
    )
    conn.commit()


def _add_subscription(conn, user_id, region_code="FR", alert_type="under_production"):
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type) VALUES (?, ?, ?)",
        (user_id, region_code, alert_type),
    )
    conn.commit()


def _user_exists(conn, user_id):
    return conn.execute(
        "SELECT COUNT(*) FROM USER_ACCOUNT WHERE id = ?", (user_id,)
    ).fetchone()[0] > 0


def _warning_sent_at(conn, user_id):
    return conn.execute(
        "SELECT inactivity_warning_sent_at FROM USER_ACCOUNT WHERE id = ?", (user_id,)
    ).fetchone()[0]


# ── _subtract_months edge cases ───────────────────────────────────────────────

def test_subtract_months_basic():
    dt = datetime(2026, 3, 11, tzinfo=timezone.utc)
    assert _subtract_months(dt, 11).strftime("%Y-%m-%d") == "2025-04-11"
    assert _subtract_months(dt, 12).strftime("%Y-%m-%d") == "2025-03-11"


def test_subtract_months_end_of_month_clamped():
    """March 31 - 1 month = February 28 (not Feb 31)."""
    dt = datetime(2026, 3, 31, tzinfo=timezone.utc)
    result = _subtract_months(dt, 1)
    assert result.strftime("%Y-%m-%d") == "2026-02-28"


def test_subtract_months_across_year_boundary():
    dt = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert _subtract_months(dt, 3).strftime("%Y-%m-%d") == "2025-10-15"


# ── Deletion (12 months) ──────────────────────────────────────────────────────

def test_account_deleted_after_12_months():
    conn = _make_db()
    _add_user(conn, 1, "old@test.com", _months_ago(14))  # clearly > 12 months
    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    assert not _user_exists(conn, 1)
    assert result["deleted"] == 1
    assert result["warned"] == 0
    mock_svc.send_inactivity_warning.assert_not_called()


def test_deletion_cascades_subscriptions():
    conn = _make_db()
    _add_user(conn, 1, "old@test.com", _months_ago(14))
    _add_subscription(conn, 1)

    run_rgpd_cleanup(conn, MagicMock())

    assert not _user_exists(conn, 1)
    sub_count = conn.execute(
        "SELECT COUNT(*) FROM ALERT_SUBSCRIPTION WHERE user_id = 1"
    ).fetchone()[0]
    assert sub_count == 0


# ── Warning (11 months) ───────────────────────────────────────────────────────

def test_warning_sent_at_11_months():
    conn = _make_db()
    _add_user(conn, 1, "almost@test.com", _in_warning_window())
    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    mock_svc.send_inactivity_warning.assert_called_once_with("almost@test.com")
    assert result["warned"] == 1
    assert result["deleted"] == 0
    assert _warning_sent_at(conn, 1) is not None
    assert _user_exists(conn, 1)


def test_warning_not_resent_if_already_warned():
    conn = _make_db()
    _add_user(conn, 1, "warned@test.com", _in_warning_window(), warning_sent_at=_recent())
    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    mock_svc.send_inactivity_warning.assert_not_called()
    assert result["warned"] == 0


# ── Recent user — no action ───────────────────────────────────────────────────

def test_recent_user_not_affected():
    conn = _make_db()
    _add_user(conn, 1, "active@test.com", _recent())
    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    assert _user_exists(conn, 1)
    mock_svc.send_inactivity_warning.assert_not_called()
    assert result["warned"] == 0
    assert result["deleted"] == 0


# ── Email failure ─────────────────────────────────────────────────────────────

def test_warning_email_failure_counted_as_error():
    conn = _make_db()
    _add_user(conn, 1, "fail@test.com", _in_warning_window())
    mock_svc = MagicMock()
    mock_svc.send_inactivity_warning.side_effect = RuntimeError("Resend down")

    result = run_rgpd_cleanup(conn, mock_svc)

    assert result["errors"] == 1
    assert result["warned"] == 0
    assert _warning_sent_at(conn, 1) is None


# ── Mixed cycle ───────────────────────────────────────────────────────────────

def test_both_warning_and_deletion_in_one_cycle():
    conn = _make_db()
    _add_user(conn, 1, "delete@test.com", _months_ago(14))    # > 12 months → delete
    _add_user(conn, 2, "warn@test.com", _in_warning_window())  # 11-12 months → warn
    _add_user(conn, 3, "active@test.com", _recent())           # recent → no-op
    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    assert not _user_exists(conn, 1)
    assert _user_exists(conn, 2)
    assert _user_exists(conn, 3)
    assert result["deleted"] == 1
    assert result["warned"] == 1
    assert result["errors"] == 0
    mock_svc.send_inactivity_warning.assert_called_once_with("warn@test.com")


# ── Counters ──────────────────────────────────────────────────────────────────

def test_return_counters_correct():
    conn = _make_db()
    _add_user(conn, 1, "del1@test.com", _months_ago(14))
    _add_user(conn, 2, "del2@test.com", _months_ago(24))
    _add_user(conn, 3, "warn@test.com", _in_warning_window())
    _add_user(conn, 4, "warned_already@test.com", _in_warning_window(), warning_sent_at=_recent())

    mock_svc = MagicMock()

    result = run_rgpd_cleanup(conn, mock_svc)

    assert result["deleted"] == 2
    assert result["warned"] == 1   # user3 only (user4 already warned)
    assert result["errors"] == 0
