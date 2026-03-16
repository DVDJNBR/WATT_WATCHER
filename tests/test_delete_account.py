"""
Tests for Story 2.5 — Delete Account

Covers: delete_account() service function.
Uses in-memory SQLite with USER_ACCOUNT + ALERT_SUBSCRIPTION + ALERT_SENT_LOG schemas.
PRAGMA foreign_keys = ON is required for cascade DELETE to work in SQLite.
"""

import sqlite3
from unittest.mock import MagicMock

from shared.api.auth_service import confirm_email, delete_account, register


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    """In-memory SQLite DB with full schema and FK enforcement enabled."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE USER_ACCOUNT (
            id                          INTEGER  PRIMARY KEY AUTOINCREMENT,
            email                       TEXT     NOT NULL UNIQUE,
            password_hash               TEXT     NOT NULL,
            is_confirmed                INTEGER  NOT NULL DEFAULT 0,
            confirmation_token          TEXT,
            confirmation_token_expires  TEXT,
            reset_token                 TEXT,
            reset_token_expires         TEXT,
            last_activity               TEXT,
            created_at                  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ALERT_SUBSCRIPTION (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER  NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT     NOT NULL,
            alert_type  TEXT     NOT NULL,
            is_active   INTEGER  NOT NULL DEFAULT 1,
            created_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ALERT_SENT_LOG (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER  NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT     NOT NULL,
            alert_type  TEXT     NOT NULL,
            sent_at     TEXT
        )
    """)
    return conn


def _make_email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    return svc


def _register_confirmed(conn: sqlite3.Connection, email: str = "user@test.com", password: str = "password123") -> int:
    """Register + confirm account, return user_id."""
    svc = _make_email_service()
    register(conn, email, password, svc)
    token = conn.execute(
        "SELECT confirmation_token FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]
    confirm_email(conn, token)
    return conn.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]


def _insert_subscription(conn: sqlite3.Connection, user_id: int, region: str = "11") -> int:
    conn.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type) VALUES (?, ?, ?)",
        (user_id, region, "under_production"),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM ALERT_SUBSCRIPTION WHERE user_id = ? AND region_code = ?", (user_id, region)
    ).fetchone()[0]


def _insert_sent_log(conn: sqlite3.Connection, user_id: int, region: str = "11") -> int:
    conn.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type) VALUES (?, ?, ?)",
        (user_id, region, "under_production"),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM ALERT_SENT_LOG WHERE user_id = ?", (user_id,)
    ).fetchone()[0]


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestDeleteAccount:

    def test_delete_removes_user_account_row(self):
        conn = _make_db()
        user_id = _register_confirmed(conn)
        delete_account(conn, user_id)
        row = conn.execute(
            "SELECT id FROM USER_ACCOUNT WHERE id = ?", (user_id,)
        ).fetchone()
        assert row is None

    def test_delete_cascades_to_alert_subscription(self):
        conn = _make_db()
        user_id = _register_confirmed(conn)
        sub_id = _insert_subscription(conn, user_id)
        delete_account(conn, user_id)
        row = conn.execute(
            "SELECT id FROM ALERT_SUBSCRIPTION WHERE id = ?", (sub_id,)
        ).fetchone()
        assert row is None

    def test_delete_cascades_to_alert_sent_log(self):
        conn = _make_db()
        user_id = _register_confirmed(conn)
        log_id = _insert_sent_log(conn, user_id)
        delete_account(conn, user_id)
        row = conn.execute(
            "SELECT id FROM ALERT_SENT_LOG WHERE id = ?", (log_id,)
        ).fetchone()
        assert row is None

    def test_delete_cascades_multiple_subscriptions(self):
        """All subscriptions for user are deleted, not just one."""
        conn = _make_db()
        user_id = _register_confirmed(conn)
        _insert_subscription(conn, user_id, region="11")
        _insert_subscription(conn, user_id, region="84")
        _insert_subscription(conn, user_id, region="93")
        delete_account(conn, user_id)
        count = conn.execute(
            "SELECT COUNT(*) FROM ALERT_SUBSCRIPTION WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        assert count == 0

    def test_delete_only_affects_target_user(self):
        """Other users' data must not be deleted."""
        conn = _make_db()
        user_id_1 = _register_confirmed(conn, email="user1@test.com")
        user_id_2 = _register_confirmed(conn, email="user2@test.com")
        _insert_subscription(conn, user_id_1)
        _insert_subscription(conn, user_id_2)
        delete_account(conn, user_id_1)
        # user2 subscription must still exist
        count = conn.execute(
            "SELECT COUNT(*) FROM ALERT_SUBSCRIPTION WHERE user_id = ?", (user_id_2,)
        ).fetchone()[0]
        assert count == 1
        # user2 account must still exist
        row = conn.execute(
            "SELECT id FROM USER_ACCOUNT WHERE id = ?", (user_id_2,)
        ).fetchone()
        assert row is not None

    def test_delete_nonexistent_user_is_idempotent(self):
        """Deleting a user that doesn't exist must not raise an exception."""
        conn = _make_db()
        delete_account(conn, 99999)  # should not raise

    def test_delete_already_deleted_user_is_idempotent(self):
        """Calling delete_account twice must not raise on second call."""
        conn = _make_db()
        user_id = _register_confirmed(conn)
        delete_account(conn, user_id)
        delete_account(conn, user_id)  # should not raise

    def test_delete_cascades_both_tables_simultaneously(self):
        """Deletion removes rows from both ALERT_SUBSCRIPTION and ALERT_SENT_LOG at once."""
        conn = _make_db()
        user_id = _register_confirmed(conn)
        sub_id = _insert_subscription(conn, user_id)
        log_id = _insert_sent_log(conn, user_id)
        delete_account(conn, user_id)
        assert conn.execute(
            "SELECT id FROM ALERT_SUBSCRIPTION WHERE id = ?", (sub_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT id FROM ALERT_SENT_LOG WHERE id = ?", (log_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT id FROM USER_ACCOUNT WHERE id = ?", (user_id,)
        ).fetchone() is None
