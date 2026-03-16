"""
Tests for Story 2.2 — Register & Email Confirmation

Covers: register, confirm_email, resend_confirmation service functions.
Uses in-memory SQLite with full USER_ACCOUNT schema (including migration 004 column).
"""

import datetime
import sqlite3
from unittest.mock import MagicMock

import bcrypt
import pytest

from shared.api.auth_service import (
    AlreadyConfirmedError,
    ConflictError,
    TokenError,
    confirm_email,
    register,
    resend_confirmation,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    """In-memory SQLite DB with USER_ACCOUNT schema (matches Azure SQL + migration 004)."""
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
    """Mock EmailService that records send_confirmation calls."""
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    return svc


def _get_row(conn: sqlite3.Connection, email: str) -> dict:
    """Fetch the USER_ACCOUNT row for given email as a dict."""
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


# ─── AC: register → 201, bcrypt, email sent ──────────────────────────────────


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
        # Stored hash must verify correctly
        assert bcrypt.checkpw(b"password123", row["password_hash"].encode("utf-8"))
        # And must NOT be the plain password
        assert row["password_hash"] != "password123"

    def test_register_account_unconfirmed_by_default(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert row["is_confirmed"] == 0

    def test_register_stores_confirmation_token(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert row["confirmation_token"] is not None
        assert len(row["confirmation_token"]) > 0

    def test_register_stores_token_expiry(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        row = _get_row(conn, "user@test.com")
        assert row["confirmation_token_expires"] is not None

    def test_register_sends_confirmation_email(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        db_token = _get_row(conn, "user@test.com")["confirmation_token"]
        svc.send_confirmation.assert_called_once_with("user@test.com", db_token)

    def test_register_normalizes_email_to_lowercase(self):
        conn = _make_db()
        svc = _make_email_service()
        result = register(conn, "User@Test.COM", "password123", svc)
        assert result["email"] == "user@test.com"
        row = _get_row(conn, "user@test.com")
        assert row is not None

    def test_register_email_send_failure_does_not_abort(self):
        """Registration succeeds even if email send throws."""
        conn = _make_db()
        svc = _make_email_service()
        svc.send_confirmation.side_effect = RuntimeError("SMTP down")
        result = register(conn, "user@test.com", "password123", svc)
        assert result["user_id"] > 0
        # Account still created
        row = _get_row(conn, "user@test.com")
        assert row["email"] == "user@test.com"


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


# ─── AC: confirm token valide → 200, token invalidé ──────────────────────────


class TestConfirmEmail:

    def test_confirm_valid_token_returns_user(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        result = confirm_email(conn, token)
        assert result["email"] == "user@test.com"
        assert isinstance(result["user_id"], int)

    def test_confirm_sets_is_confirmed(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        confirm_email(conn, token)
        row = _get_row(conn, "user@test.com")
        assert row["is_confirmed"] == 1

    def test_confirm_invalidates_token(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        confirm_email(conn, token)
        row = _get_row(conn, "user@test.com")
        assert row["confirmation_token"] is None
        assert row["confirmation_token_expires"] is None

    def test_confirm_unknown_token_raises_token_error(self):
        conn = _make_db()
        with pytest.raises(TokenError):
            confirm_email(conn, "unknown-token-xyz")

    def test_confirm_empty_token_raises_token_error(self):
        conn = _make_db()
        with pytest.raises(TokenError):
            confirm_email(conn, "")

    def test_confirm_already_confirmed_raises_token_error(self):
        """Once confirmed, token is NULL → re-confirm raises TokenError (token not found)."""
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        confirm_email(conn, token)
        # Token was invalidated (set to NULL) — re-use raises TokenError
        with pytest.raises(TokenError):
            confirm_email(conn, token)

    def test_confirm_expired_token_raises_token_error(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        # Retroactively expire the token
        past = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        conn.execute(
            "UPDATE USER_ACCOUNT SET confirmation_token_expires = ? WHERE email = ?",
            (past.isoformat(), "user@test.com"),
        )
        conn.commit()
        with pytest.raises(TokenError, match="expired"):
            confirm_email(conn, token)


# ─── AC: resend-confirmation ──────────────────────────────────────────────────


class TestResendConfirmation:

    def test_resend_unconfirmed_sends_email(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        svc.send_confirmation.reset_mock()
        result = resend_confirmation(conn, "user@test.com", svc)
        assert "confirmation email" in result["message"]
        svc.send_confirmation.assert_called_once()

    def test_resend_generates_new_token(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        old_token = _get_row(conn, "user@test.com")["confirmation_token"]
        resend_confirmation(conn, "user@test.com", svc)
        new_token = _get_row(conn, "user@test.com")["confirmation_token"]
        assert new_token != old_token

    def test_resend_unknown_email_returns_200_no_leak(self):
        conn = _make_db()
        svc = _make_email_service()
        result = resend_confirmation(conn, "unknown@test.com", svc)
        assert "confirmation email" in result["message"]
        svc.send_confirmation.assert_not_called()

    def test_resend_already_confirmed_raises(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        token = _get_row(conn, "user@test.com")["confirmation_token"]
        confirm_email(conn, token)
        with pytest.raises(AlreadyConfirmedError):
            resend_confirmation(conn, "user@test.com", svc)

    def test_resend_email_failure_does_not_raise(self):
        """Resend returns success even if email send fails."""
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        svc.send_confirmation.side_effect = RuntimeError("SMTP down")
        result = resend_confirmation(conn, "user@test.com", svc)
        assert "message" in result

    def test_resend_normalizes_email(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        svc.send_confirmation.reset_mock()
        result = resend_confirmation(conn, "USER@TEST.COM", svc)
        assert "confirmation email" in result["message"]
        svc.send_confirmation.assert_called_once()
