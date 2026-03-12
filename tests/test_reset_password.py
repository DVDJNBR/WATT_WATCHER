"""
Tests for Story 2.4 — Reset Password

Covers: request_password_reset(), confirm_password_reset() service functions.
Uses in-memory SQLite with full USER_ACCOUNT schema.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import bcrypt
import pytest

from shared.api.auth_service import (
    TokenError,
    confirm_email,
    confirm_password_reset,
    login,
    register,
    request_password_reset,
)

JWT_SECRET = "test-jwt-secret-for-reset-tests-32b"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    """In-memory SQLite DB with full USER_ACCOUNT schema."""
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
            last_activity               TEXT,
            created_at                  TEXT
        )
    """)
    return conn


def _make_email_service() -> MagicMock:
    svc = MagicMock()
    svc.send_confirmation = MagicMock()
    svc.send_reset = MagicMock()
    return svc


def _register_confirmed(conn: sqlite3.Connection, email: str = "user@test.com", password: str = "password123"):
    """Register + confirm a user account in one step."""
    svc = _make_email_service()
    register(conn, email, password, svc)
    token = conn.execute(
        "SELECT confirmation_token FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]
    confirm_email(conn, token)


def _get_reset_token(conn: sqlite3.Connection, email: str) -> str:
    """Retrieve the reset_token stored in DB for given email."""
    return conn.execute(
        "SELECT reset_token FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]


# ─── AC #1: request_password_reset — no info leak ─────────────────────────────


class TestRequestPasswordReset:

    def test_known_email_returns_generic_message(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        result = request_password_reset(conn, "user@test.com", svc)
        assert "message" in result
        assert len(result["message"]) > 0

    def test_unknown_email_returns_same_message(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        result_known = request_password_reset(conn, "user@test.com", svc)
        svc2 = _make_email_service()
        result_unknown = request_password_reset(conn, "nobody@test.com", svc2)
        assert result_known["message"] == result_unknown["message"]

    def test_known_email_sends_reset_email(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        request_password_reset(conn, "user@test.com", svc)
        svc.send_reset.assert_called_once()
        call_args = svc.send_reset.call_args
        assert call_args[0][0] == "user@test.com"  # first arg = email

    def test_known_email_send_reset_called_with_db_token(self):
        """send_reset must be called with the token stored in DB, not a generated one."""
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        request_password_reset(conn, "user@test.com", svc)
        db_token = _get_reset_token(conn, "user@test.com")
        svc.send_reset.assert_called_once_with("user@test.com", db_token)

    def test_unknown_email_does_not_call_send_reset(self):
        conn = _make_db()
        svc = _make_email_service()
        request_password_reset(conn, "nobody@test.com", svc)
        svc.send_reset.assert_not_called()

    def test_email_send_failure_does_not_propagate(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        svc.send_reset.side_effect = RuntimeError("SMTP down")
        # Should not raise
        result = request_password_reset(conn, "user@test.com", svc)
        assert "message" in result

    def test_normalizes_email(self):
        conn = _make_db()
        _register_confirmed(conn, email="user@test.com")
        svc = _make_email_service()
        result = request_password_reset(conn, "USER@TEST.COM", svc)
        # Known email (after normalization) → send_reset called
        svc.send_reset.assert_called_once()

    def test_stores_reset_token_in_db(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        request_password_reset(conn, "user@test.com", svc)
        token = _get_reset_token(conn, "user@test.com")
        assert token is not None
        assert len(token) > 0

    def test_stores_reset_token_expires_in_db(self):
        conn = _make_db()
        _register_confirmed(conn)
        svc = _make_email_service()
        request_password_reset(conn, "user@test.com", svc)
        expires = conn.execute(
            "SELECT reset_token_expires FROM USER_ACCOUNT WHERE email = ?", ("user@test.com",)
        ).fetchone()[0]
        assert expires is not None


# ─── AC #2+3: confirm_password_reset ─────────────────────────────────────────


class TestConfirmPasswordReset:

    @pytest.fixture(autouse=True)
    def set_jwt_secret(self, monkeypatch):
        """Required for login() calls in tests that verify the new password works."""
        from shared.api import auth
        auth.reset_jwt_secret()
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
        yield
        auth.reset_jwt_secret()

    def _setup_reset(self, conn, email="user@test.com", password="password123"):
        """Register, confirm, then request reset. Returns reset token."""
        _register_confirmed(conn, email, password)
        svc = _make_email_service()
        request_password_reset(conn, email, svc)
        return _get_reset_token(conn, email)

    def test_valid_token_returns_user_id_and_email(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        result = confirm_password_reset(conn, token, "newpass456")
        assert result["email"] == "user@test.com"
        assert isinstance(result["user_id"], int) and result["user_id"] > 0

    def test_new_password_is_hashed_and_login_works(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        # Login with old password must fail
        from shared.api.auth_service import AuthError
        with pytest.raises(AuthError):
            login(conn, "user@test.com", "password123")
        # Login with new password must succeed
        result = login(conn, "user@test.com", "newpass456")
        assert "token" in result

    def test_token_is_nulled_after_use(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        db_token = _get_reset_token(conn, "user@test.com")
        assert db_token is None

    def test_last_activity_updated(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        row = conn.execute(
            "SELECT last_activity FROM USER_ACCOUNT WHERE email = ?", ("user@test.com",)
        ).fetchone()
        assert row[0] is not None

    def test_unknown_token_raises_token_error(self):
        conn = _make_db()
        _register_confirmed(conn)
        with pytest.raises(TokenError):
            confirm_password_reset(conn, "totally-fake-token", "newpass456")

    def test_expired_token_raises_token_error(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        # Backdated expires by 2 hours
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        conn.execute(
            "UPDATE USER_ACCOUNT SET reset_token_expires = ? WHERE reset_token = ?",
            (past.isoformat(), token),
        )
        conn.commit()
        with pytest.raises(TokenError):
            confirm_password_reset(conn, token, "newpass456")

    def test_already_used_token_raises_token_error(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        # Second use of same token
        with pytest.raises(TokenError):
            confirm_password_reset(conn, token, "anotherpass")

    def test_empty_new_password_raises_value_error(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        with pytest.raises(ValueError):
            confirm_password_reset(conn, token, "")

    def test_empty_token_raises_token_error(self):
        conn = _make_db()
        with pytest.raises(TokenError):
            confirm_password_reset(conn, "", "newpass456")

    def test_new_password_hashed_with_bcrypt(self):
        """Verify the stored password_hash is a valid bcrypt hash."""
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        hash_stored = conn.execute(
            "SELECT password_hash FROM USER_ACCOUNT WHERE email = ?", ("user@test.com",)
        ).fetchone()[0]
        assert bcrypt.checkpw(b"newpass456", hash_stored.encode("utf-8"))

    def test_reset_token_expires_cleared_after_use(self):
        conn = _make_db()
        token = self._setup_reset(conn)
        confirm_password_reset(conn, token, "newpass456")
        expires = conn.execute(
            "SELECT reset_token_expires FROM USER_ACCOUNT WHERE email = ?", ("user@test.com",)
        ).fetchone()[0]
        assert expires is None

    def test_naive_expiry_datetime_handled(self):
        """Naive datetime in expires (stored by older code using utcnow()) must not crash."""
        conn = _make_db()
        token = self._setup_reset(conn)
        # Store a naive datetime string (no timezone info)
        future_naive = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            "UPDATE USER_ACCOUNT SET reset_token_expires = ? WHERE reset_token = ?",
            (future_naive, token),
        )
        conn.commit()
        # Should not raise TypeError from comparing aware vs naive
        result = confirm_password_reset(conn, token, "newpass456")
        assert result["email"] == "user@test.com"

    def test_null_expires_raises_token_error(self):
        """Token with NULL reset_token_expires must be rejected, not treated as never-expiring."""
        conn = _make_db()
        token = self._setup_reset(conn)
        conn.execute(
            "UPDATE USER_ACCOUNT SET reset_token_expires = NULL WHERE reset_token = ?",
            (token,),
        )
        conn.commit()
        with pytest.raises(TokenError):
            confirm_password_reset(conn, token, "newpass456")

    def test_whitespace_only_password_raises_value_error(self):
        """Password of only whitespace must be rejected."""
        conn = _make_db()
        token = self._setup_reset(conn)
        with pytest.raises(ValueError):
            confirm_password_reset(conn, token, "   ")

    def test_unconfirmed_account_does_not_receive_reset_email(self):
        """request_password_reset must not send email to unconfirmed accounts."""
        conn = _make_db()
        svc = _make_email_service()
        # Register but do NOT confirm
        register(conn, "unconfirmed@test.com", "password123", svc)
        svc2 = _make_email_service()
        result = request_password_reset(conn, "unconfirmed@test.com", svc2)
        # Same generic message
        assert "message" in result
        # But send_reset must NOT have been called
        svc2.send_reset.assert_not_called()

    def test_unconfirmed_account_returns_generic_message(self):
        """Unconfirmed account must return the same generic message as unknown email (no info leak)."""
        conn = _make_db()
        svc_reg = _make_email_service()
        register(conn, "unconfirmed@test.com", "password123", svc_reg)
        svc = _make_email_service()
        result_unconfirmed = request_password_reset(conn, "unconfirmed@test.com", svc)
        svc2 = _make_email_service()
        result_unknown = request_password_reset(conn, "nobody@test.com", svc2)
        assert result_unconfirmed["message"] == result_unknown["message"]
