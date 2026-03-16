"""
Tests for subscription_service.py — Story 4.1.

AC #1: GET returns active subscriptions (is_active=1) for user.
AC #2: PUT replaces all subscriptions (DELETE all + INSERT new).
AC #3: Format: [{"region_code": str, "alert_type": str, "is_active": bool}]
AC #4: alert_type validated: "under_production" or "over_production".
AC #5: Duplicate (region_code, alert_type) in PUT payload → ValueError.
"""

import sqlite3

from shared.api.subscription_service import get_subscriptions, update_subscriptions


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmation_token TEXT, confirmation_token_expires TEXT,
            reset_token TEXT, reset_token_expires TEXT,
            last_activity TEXT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ALERT_SUBSCRIPTION (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.execute("INSERT INTO USER_ACCOUNT (id, email, password_hash) VALUES (1, 'u@t.com', 'h')")
    conn.execute("INSERT INTO USER_ACCOUNT (id, email, password_hash) VALUES (2, 'v@t.com', 'h')")
    conn.commit()
    return conn


# ── GET tests ────────────────────────────────────────────────────────────────

def test_get_no_subscriptions():
    conn = _make_db()
    result = get_subscriptions(conn, 1)
    assert result == []


def test_get_returns_only_active():
    conn = _make_db()
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) VALUES (1, 'FR', 'under_production', 1)"
    )
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) VALUES (1, 'BE', 'over_production', 0)"
    )
    conn.commit()
    result = get_subscriptions(conn, 1)
    assert len(result) == 1
    assert result[0]["region_code"] == "FR"
    assert result[0]["alert_type"] == "under_production"
    assert result[0]["is_active"] is True


def test_get_returns_only_own_subscriptions():
    conn = _make_db()
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) VALUES (1, 'FR', 'under_production', 1)"
    )
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) VALUES (2, 'DE', 'over_production', 1)"
    )
    conn.commit()
    result = get_subscriptions(conn, 1)
    assert len(result) == 1
    assert result[0]["region_code"] == "FR"


# ── PUT tests ────────────────────────────────────────────────────────────────

def test_put_empty_list_deletes_all():
    conn = _make_db()
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type, is_active) VALUES (1, 'FR', 'under_production', 1)"
    )
    conn.commit()
    result = update_subscriptions(conn, 1, [])
    assert result == []
    assert get_subscriptions(conn, 1) == []


def test_put_inserts_and_returns_subscriptions():
    conn = _make_db()
    payload = [
        {"region_code": "FR", "alert_type": "under_production"},
        {"region_code": "BE", "alert_type": "over_production"},
    ]
    result = update_subscriptions(conn, 1, payload)
    assert len(result) == 2
    assert result[0]["region_code"] == "FR"
    assert result[0]["alert_type"] == "under_production"
    assert result[0]["is_active"] is True
    assert result[1]["region_code"] == "BE"
    assert result[1]["alert_type"] == "over_production"


def test_put_replaces_existing_subscriptions():
    conn = _make_db()
    update_subscriptions(conn, 1, [{"region_code": "FR", "alert_type": "under_production"}])
    result = update_subscriptions(conn, 1, [{"region_code": "DE", "alert_type": "over_production"}])
    assert len(result) == 1
    assert result[0]["region_code"] == "DE"
    final = get_subscriptions(conn, 1)
    assert len(final) == 1
    assert final[0]["region_code"] == "DE"


def test_get_after_put_returns_updated_list():
    conn = _make_db()
    update_subscriptions(conn, 1, [{"region_code": "FR", "alert_type": "under_production"}])
    update_subscriptions(conn, 1, [
        {"region_code": "BE", "alert_type": "under_production"},
        {"region_code": "ES", "alert_type": "over_production"},
    ])
    result = get_subscriptions(conn, 1)
    region_codes = {r["region_code"] for r in result}
    assert region_codes == {"BE", "ES"}


def test_put_is_active_false():
    conn = _make_db()
    payload = [{"region_code": "FR", "alert_type": "under_production", "is_active": False}]
    result = update_subscriptions(conn, 1, payload)
    assert result[0]["is_active"] is False


# ── Validation error tests ────────────────────────────────────────────────────

def test_put_invalid_alert_type_raises():
    conn = _make_db()
    try:
        update_subscriptions(conn, 1, [{"region_code": "FR", "alert_type": "bad_type"}])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "bad_type" in str(e)


def test_put_duplicate_raises():
    conn = _make_db()
    payload = [
        {"region_code": "FR", "alert_type": "under_production"},
        {"region_code": "FR", "alert_type": "under_production"},
    ]
    try:
        update_subscriptions(conn, 1, payload)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Duplicate" in str(e)


def test_put_empty_region_code_raises():
    conn = _make_db()
    try:
        update_subscriptions(conn, 1, [{"region_code": "", "alert_type": "under_production"}])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "region_code" in str(e)


def test_put_whitespace_region_code_raises():
    conn = _make_db()
    try:
        update_subscriptions(conn, 1, [{"region_code": "   ", "alert_type": "under_production"}])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "region_code" in str(e)


def test_put_validation_error_does_not_delete_existing():
    """If validation fails, no DB changes should occur."""
    conn = _make_db()
    update_subscriptions(conn, 1, [{"region_code": "FR", "alert_type": "under_production"}])
    try:
        update_subscriptions(conn, 1, [
            {"region_code": "DE", "alert_type": "under_production"},
            {"region_code": "DE", "alert_type": "under_production"},  # duplicate
        ])
    except ValueError:
        pass
    # Original subscription should still be there
    result = get_subscriptions(conn, 1)
    assert len(result) == 1
    assert result[0]["region_code"] == "FR"
