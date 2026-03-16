"""
Tests for Story 2.3 — Login & Logout

Covers: login(), logout(), _generate_jwt() service functions.
Uses in-memory SQLite with full USER_ACCOUNT schema.
"""

import datetime
import sqlite3
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest

from shared.api.auth_service import (
    AuthError,
    UnconfirmedError,
    login,
    logout,
    _generate_jwt,
    register,
    confirm_email,
)

JWT_SECRET = "test-jwt-secret-for-login-tests-32b"


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
    return svc


def _register_confirmed(conn: sqlite3.Connection, email: str = "user@test.com", password: str = "password123"):
    """Register + confirm a user account in one step."""
    svc = _make_email_service()
    register(conn, email, password, svc)
    token = conn.execute(
        "SELECT confirmation_token FROM USER_ACCOUNT WHERE email = ?", (email,)
    ).fetchone()[0]
    confirm_email(conn, token)


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Inject JWT secret and reset cache before/after each test."""
    from shared.api import auth
    auth.reset_jwt_secret()
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    yield
    auth.reset_jwt_secret()


# ─── AC: login valide → JWT 24h ──────────────────────────────────────────────


class TestLoginValid:

    def test_login_returns_token_user_id_email(self):
        conn = _make_db()
        _register_confirmed(conn)
        result = login(conn, "user@test.com", "password123")
        assert "token" in result
        assert result["email"] == "user@test.com"
        assert isinstance(result["user_id"], int) and result["user_id"] > 0

    def test_login_token_is_valid_jwt(self):
        conn = _make_db()
        _register_confirmed(conn)
        result = login(conn, "user@test.com", "password123")
        payload = pyjwt.decode(result["token"], JWT_SECRET, algorithms=["HS256"])
        assert payload["email"] == "user@test.com"
        assert payload["user_id"] == result["user_id"]

    def test_login_token_expires_in_24h(self):
        conn = _make_db()
        _register_confirmed(conn)
        result = login(conn, "user@test.com", "password123")
        payload = pyjwt.decode(result["token"], JWT_SECRET, algorithms=["HS256"])
        now = datetime.datetime.utcnow()
        exp = datetime.datetime.utcfromtimestamp(payload["exp"])
        diff_hours = (exp - now).total_seconds() / 3600
        assert 23 < diff_hours < 25

    def test_login_token_has_iat_claim(self):
        conn = _make_db()
        _register_confirmed(conn)
        result = login(conn, "user@test.com", "password123")
        payload = pyjwt.decode(result["token"], JWT_SECRET, algorithms=["HS256"])
        assert "iat" in payload

    def test_login_normalizes_email(self):
        conn = _make_db()
        _register_confirmed(conn, email="user@test.com")
        result = login(conn, "USER@TEST.COM", "password123")
        assert result["email"] == "user@test.com"

    def test_login_updates_last_activity(self):
        conn = _make_db()
        _register_confirmed(conn)
        login(conn, "user@test.com", "password123")
        row = conn.execute(
            "SELECT last_activity FROM USER_ACCOUNT WHERE email = ?", ("user@test.com",)
        ).fetchone()
        assert row[0] is not None


# ─── AC: mauvais mot de passe → 401 générique ────────────────────────────────


class TestLoginBadCredentials:

    def test_wrong_password_raises_auth_error(self):
        conn = _make_db()
        _register_confirmed(conn)
        with pytest.raises(AuthError):
            login(conn, "user@test.com", "wrongpassword")

    def test_unknown_email_raises_auth_error(self):
        conn = _make_db()
        with pytest.raises(AuthError):
            login(conn, "nobody@test.com", "password123")

    def test_error_messages_are_identical(self):
        """Wrong password and unknown email must produce the SAME message — no info leak."""
        conn = _make_db()
        _register_confirmed(conn)

        msg_wrong_pw = None
        msg_unknown_email = None

        try:
            login(conn, "user@test.com", "wrongpassword")
        except AuthError as e:
            msg_wrong_pw = str(e)

        try:
            login(conn, "nobody@test.com", "password123")
        except AuthError as e:
            msg_unknown_email = str(e)

        assert msg_wrong_pw is not None
        assert msg_wrong_pw == msg_unknown_email


# ─── AC: compte non confirmé → 403 ───────────────────────────────────────────


class TestLoginUnconfirmed:

    def test_unconfirmed_account_raises_unconfirmed_error(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)  # sans confirm
        with pytest.raises(UnconfirmedError):
            login(conn, "user@test.com", "password123")

    def test_unconfirmed_error_message_mentions_email(self):
        conn = _make_db()
        svc = _make_email_service()
        register(conn, "user@test.com", "password123", svc)
        try:
            login(conn, "user@test.com", "password123")
        except UnconfirmedError as e:
            assert "email" in str(e).lower()


# ─── AC: logout → 200 ────────────────────────────────────────────────────────


class TestLogout:

    def test_logout_returns_message(self):
        result = logout()
        assert "message" in result
        assert len(result["message"]) > 0

    def test_logout_is_stateless_no_conn_needed(self):
        """Logout requires no DB connection — purely stateless."""
        result = logout()
        assert result is not None


# ─── _generate_jwt internals ──────────────────────────────────────────────────


class TestGenerateJwt:

    def test_generate_jwt_returns_string(self):
        token = _generate_jwt(1, "user@test.com")
        assert isinstance(token, str)

    def test_generate_jwt_payload_correct(self):
        token = _generate_jwt(42, "dev@test.com")
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        assert payload["user_id"] == 42
        assert payload["email"] == "dev@test.com"

    def test_generate_jwt_different_users_different_tokens(self):
        t1 = _generate_jwt(1, "alice@test.com")
        t2 = _generate_jwt(2, "bob@test.com")
        assert t1 != t2
