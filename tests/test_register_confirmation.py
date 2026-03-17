"""
Tests for Story 2.2 — Register (auto-confirm flow)

Email confirmation flow removed: accounts are confirmed at insert time.
Covers: register service function — bcrypt, validation, duplicates, auto-confirm.
"""

import sqlite3
from unittest.mock import MagicMock

import bcrypt
import pytest

from shared.api.auth_service import (
    ConflictError,
    register,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
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
            last_activity               TEXT     NOT NULL DEFAULT (datetime('now')),
            created_at                  TEXT     NOT NULL DEFAULT (datetime('now'))
        )
    """)
    return conn


def _make_email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    return svc


def _get_row(conn: sqlite3.Connection, email: str) -> dict:
    cursor = conn.execute(
        "SELECT id, email, password_hash, is_confirmed, "
        "confirmation_token, confirmation_token_expires "
        "FROM USER_ACCOUNT WHERE email = ?",
        (email,),
    )
    row = cursor.fetchone()
    if not row:
        return {}
    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "is_confirmed": row[3],
        "confirmation_token": row[4],
        "confirmation_token_expires": row[5],
    }


# ─── AC: register → 201, bcrypt, auto-confirmed ───────────────────────────────


class TestRegister:

    def test_register_returns_user_id_and_email(self):
        conn = _make_db()
        svc = _make_email_service()
        result = register(conn, "user@test.com", "password123", svc)
        assert result["email"] == "user@test.com"
        assert isinstance(result["user_id"], int)
        assert result["user_id"] > 0

    def test_register_hashes_password_with_bcrypt(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert bcrypt.checkpw(b"password123", row["password_hash"].encode("utf-8"))
        assert row["password_hash"] != "password123"

    def test_register_account_confirmed_by_default(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert row["is_confirmed"] == 1

    def test_register_no_confirmation_token(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert row["confirmation_token"] is None
        assert row["confirmation_token_expires"] is None

    def test_register_does_not_send_confirmation_email(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        svc.send_confirmation.assert_not_called()

    def test_register_normalizes_email_to_lowercase(self):
        conn = _make_db()
        svc = _make_email_service()
        result = register(conn, "User@Test.COM", "password123", svc)
        assert result["email"] == "user@test.com"
        assert _get_row(conn, "user@test.com") != {}

    def test_register_email_send_failure_does_not_abort(self):
        """Registration succeeds even if email service throws (fire-and-forget)."""
        conn = _make_db()
        svc = _make_email_service()
        svc.send_confirmation.side_effect = RuntimeError("SMTP down")
        result = register(conn, "user@test.com", "password123", svc)
        assert result["user_id"] > 0


# ─── AC: email déjà existant → 409 Conflict ──────────────────────────────────


class TestRegisterDuplicate:

    def test_duplicate_email_raises_conflict_error(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        with pytest.raises(ConflictError):
            register(conn, "user@test.com", "anotherpassword", svc)

    def test_duplicate_email_case_insensitive(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        with pytest.raises(ConflictError):
            register(conn, "USER@TEST.COM", "anotherpassword", svc)


# ─── AC: validation format email ─────────────────────────────────────────────


class TestRegisterEmailValidation:

    @pytest.mark.parametrize("bad_email", [
        "notanemail",
        "missing@",
        "@nodomain.com",
        "no spaces@test.com",
        "",
        "a" * 256 + "@test.com",
    ])
    def test_invalid_email_raises_value_error(self, bad_email):
        conn = _make_db()
        svc = _make_email_service()
        with pytest.raises(ValueError):
            register(conn, bad_email, "password123", svc)

    @pytest.mark.parametrize("good_email", [
        "user@test.com",
        "user+tag@example.co.uk",
        "first.last@sub.domain.com",
    ])
    def test_valid_email_accepted(self, good_email):
        conn = _make_db()
        svc = _make_email_service()
        result = register(conn, good_email, "password123", svc)
        assert result["user_id"] > 0
