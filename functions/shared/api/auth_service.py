"""
Auth Service — Story 2.2

Handles: register, confirm_email, resend_confirmation.
Login/logout/reset/delete will be added in stories 2.3/2.4/2.5.

DB compatibility: works with both pyodbc (Azure SQL) and sqlite3 (local/tests).
Both use '?' as placeholder. pyodbc returns datetime objects; sqlite3 returns strings.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt as pyjwt

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
TOKEN_EXPIRY_HOURS = 1


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ConflictError(Exception):
    """Email already registered."""


class TokenError(Exception):
    """Token invalid, expired, or already used."""


class AlreadyConfirmedError(Exception):
    """Account is already confirmed — resend not applicable."""


class AuthError(Exception):
    """Bad credentials — wrong password or unknown email. Always use generic message."""


class UnconfirmedError(Exception):
    """Account exists but email not confirmed."""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_email_valid(email: str) -> bool:
    """Basic server-side email format validation."""
    return bool(email) and len(email) <= 255 and bool(EMAIL_REGEX.match(email))


def _parse_datetime(value: Any) -> datetime:
    """
    Normalize datetime from DB row.

    pyodbc (Azure SQL) → already a datetime object.
    sqlite3 → ISO string like "2026-03-10 14:30:00.123456"
    """
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


# ── Public service functions ──────────────────────────────────────────────────

def register(conn: Any, email: str, password: str, email_service: Any) -> dict:
    """
    Register a new user account.

    Steps:
    1. Validate email format.
    2. Check for duplicate email → ConflictError.
    3. Hash password with bcrypt cost=12.
    4. Generate UUID v4 confirmation token (expires in 1h).
    5. Insert into USER_ACCOUNT.
    6. Send confirmation email (fire-and-forget — email failure doesn't abort registration).

    Returns:
        {"user_id": int, "email": str}

    Raises:
        ValueError: invalid email format.
        ConflictError: email already exists.
    """
    email = email.lower().strip()

    if not _is_email_valid(email):
        raise ValueError("Invalid email format")

    cursor = conn.cursor()

    # Check for duplicate email
    cursor.execute("SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,))
    if cursor.fetchone():
        raise ConflictError("Email already registered")

    # Hash password — bcrypt cost=12
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    # Generate confirmation token
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

    try:
        cursor.execute(
            """
            INSERT INTO USER_ACCOUNT
                (email, password_hash, is_confirmed, confirmation_token, confirmation_token_expires)
            VALUES (?, ?, 0, ?, ?)
            """,
            (email, password_hash, token, expires),
        )
        conn.commit()
    except Exception as exc:
        # UNIQUE constraint violation — race condition between SELECT and INSERT
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "integrity" in exc_str:
            raise ConflictError("Email already registered") from exc
        raise

    # Retrieve the generated user_id
    # Note: cursor.lastrowid is unreliable with pyodbc — use SELECT instead
    cursor.execute("SELECT id FROM USER_ACCOUNT WHERE email = ?", (email,))
    row = cursor.fetchone()
    user_id = row[0]

    # Send confirmation email — fire-and-forget
    try:
        email_service.send_confirmation(email, token)
    except Exception as exc:
        logger.error(
            "Failed to send confirmation email to %s: %s", email, exc, exc_info=True
        )
        # Do NOT re-raise — registration succeeds even if email send fails

    return {"user_id": user_id, "email": email}


def confirm_email(conn: Any, token: str) -> dict:
    """
    Confirm a user's email address via confirmation token.

    Steps:
    1. Look up account by token → TokenError if not found.
    2. Check is_confirmed flag → TokenError if already confirmed.
    3. Check expiry → TokenError if expired.
    4. Mark account confirmed and invalidate token.

    Returns:
        {"user_id": int, "email": str}

    Raises:
        TokenError: token not found, already used, or expired.
    """
    if not token:
        raise TokenError("Confirmation token is required")

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, email, is_confirmed, confirmation_token_expires
        FROM USER_ACCOUNT
        WHERE confirmation_token = ?
        """,
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        raise TokenError("Invalid or unknown confirmation token")

    user_id, email, is_confirmed, expires_raw = row

    if is_confirmed:
        raise TokenError("Token already used — account is already confirmed")

    if expires_raw is not None:
        expires = _parse_datetime(expires_raw)
        if datetime.utcnow() > expires:
            raise TokenError("Confirmation token has expired")

    # Activate account and invalidate token
    cursor.execute(
        """
        UPDATE USER_ACCOUNT
        SET is_confirmed = 1,
            confirmation_token = NULL,
            confirmation_token_expires = NULL
        WHERE id = ?
        """,
        (user_id,),
    )
    conn.commit()

    return {"user_id": user_id, "email": email}


def resend_confirmation(conn: Any, email: str, email_service: Any) -> dict:
    """
    Resend confirmation email for an unconfirmed account.

    Security: always returns the same message whether the email exists or not
    (no information leak about registered emails).

    Steps:
    1. Look up account by email.
    2. If not found → return silently (no leak).
    3. If already confirmed → AlreadyConfirmedError.
    4. Generate new token + expiry.
    5. Send confirmation email (fire-and-forget).

    Returns:
        {"message": str}

    Raises:
        AlreadyConfirmedError: account is already confirmed.
    """
    email = email.lower().strip()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, is_confirmed FROM USER_ACCOUNT WHERE email = ?", (email,)
    )
    row = cursor.fetchone()

    if not row:
        # Silent return — don't reveal whether email is registered
        return {"message": "If the account exists, a confirmation email has been sent"}

    user_id, is_confirmed = row

    if is_confirmed:
        raise AlreadyConfirmedError("Account is already confirmed")

    # Generate fresh token + expiry
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

    cursor.execute(
        """
        UPDATE USER_ACCOUNT
        SET confirmation_token = ?, confirmation_token_expires = ?
        WHERE id = ?
        """,
        (token, expires, user_id),
    )
    conn.commit()

    # Send email — fire-and-forget
    try:
        email_service.send_confirmation(email, token)
    except Exception as exc:
        logger.error(
            "Failed to resend confirmation email to %s: %s", email, exc, exc_info=True
        )

    return {"message": "If the account exists, a confirmation email has been sent"}


# ── Login / Logout (Story 2.3) ────────────────────────────────────────────────

JWT_EXPIRY_HOURS = 24
_AUTH_ERROR_MESSAGE = "Invalid email or password"  # single constant — ensures identical messages

# Dummy hash used in login() to equalize response time for unknown emails (prevents timing oracle).
# Generated once at import time with same bcrypt cost as real passwords.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalization-dummy", bcrypt.gensalt(rounds=12)).decode("utf-8")


def login(conn: Any, email: str, password: str) -> dict:
    """
    Authenticate a user and return a signed JWT.

    Steps:
    1. Normalize email.
    2. Fetch account by email.
    3. Check password with bcrypt.
    4. Check is_confirmed → UnconfirmedError if not.
    5. Update last_activity.
    6. Generate and return JWT.

    Returns:
        {"user_id": int, "email": str, "token": str}

    Raises:
        AuthError: wrong password or unknown email (same generic message — no info leak).
        UnconfirmedError: account exists but email not confirmed.
    """
    email = email.lower().strip()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, password_hash, is_confirmed FROM USER_ACCOUNT WHERE email = ?",
        (email,),
    )
    row = cursor.fetchone()

    if row:
        user_id, db_email, password_hash, is_confirmed = row
        password_ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    else:
        # Always run bcrypt to prevent timing-based email enumeration
        bcrypt.checkpw(password.encode("utf-8"), _DUMMY_HASH.encode("utf-8"))
        password_ok = False

    if not password_ok:
        raise AuthError(_AUTH_ERROR_MESSAGE)

    # row is guaranteed non-None here (password_ok=True implies row was found)
    if not is_confirmed:
        raise UnconfirmedError("Account not confirmed — please check your email")

    cursor.execute(
        "UPDATE USER_ACCOUNT SET last_activity = ? WHERE id = ?",
        (datetime.now(timezone.utc), user_id),
    )
    conn.commit()

    token = _generate_jwt(user_id, db_email)
    return {"user_id": user_id, "email": db_email, "token": token}


def _generate_jwt(user_id: int, email: str) -> str:
    """
    Generate a signed HS256 JWT with 24h expiry.

    Reuses _load_jwt_secret() from auth.py — shared cache, no duplication.
    PyJWT 2.x: encode() returns str directly (no .decode() needed).
    """
    from shared.api.auth import _load_jwt_secret
    secret = _load_jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": now,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def logout() -> dict:
    """
    No-op for stateless JWT.

    JWT invalidation is handled client-side (delete from localStorage).
    Server has no token store to clear.
    """
    return {"message": "Logged out successfully"}


# ── Delete Account (Story 2.5) ────────────────────────────────────────────────

def delete_account(conn: Any, user_id: int) -> None:
    """
    Permanently delete a user account and all associated data.

    The ON DELETE CASCADE constraints on ALERT_SUBSCRIPTION and ALERT_SENT_LOG
    handle cleanup of linked rows automatically.

    Args:
        conn: DB connection (pyodbc or sqlite3).
        user_id: ID of the account to delete.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM USER_ACCOUNT WHERE id = ?", (user_id,))
    conn.commit()


# ── Reset Password (Story 2.4) ────────────────────────────────────────────────

_RESET_SILENT_MESSAGE = "If the account exists, a reset email has been sent"


def request_password_reset(conn: Any, email: str, email_service: Any) -> dict:
    """
    Initiate password reset flow.

    Security: always returns the same message whether the email exists or not
    (no information leak about registered emails).

    Steps:
    1. Normalize email.
    2. Look up account by email.
    3. If not found → return silently (no leak).
    4. Generate UUID v4 reset token (expires in 1h).
    5. Update USER_ACCOUNT.reset_token / reset_token_expires.
    6. Send reset email (fire-and-forget).

    Returns:
        {"message": str}
    """
    email = email.lower().strip()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email = ? AND is_confirmed = 1", (email,)
    )
    row = cursor.fetchone()

    if not row:
        return {"message": _RESET_SILENT_MESSAGE}

    user_id = row[0]
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    cursor.execute(
        "UPDATE USER_ACCOUNT SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
        (token, expires, user_id),
    )
    conn.commit()

    try:
        email_service.send_reset(email, token)
    except Exception as exc:
        logger.error(
            "Failed to send reset email to %s: %s", email, exc, exc_info=True
        )

    return {"message": _RESET_SILENT_MESSAGE}


def confirm_password_reset(conn: Any, token: str, new_password: str) -> dict:
    """
    Apply a new password via reset token.

    Steps:
    1. Validate inputs.
    2. Look up account by reset_token → TokenError if not found.
    3. Check expiry → TokenError if expired.
    4. Hash new password with bcrypt cost=12.
    5. Update password_hash, clear reset_token, update last_activity.

    Returns:
        {"user_id": int, "email": str}

    Raises:
        TokenError: token not found or expired.
        ValueError: new_password is empty.
    """
    if not token:
        raise TokenError("Reset token is required")
    if not new_password or not new_password.strip():
        raise ValueError("New password cannot be empty")

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, email, reset_token_expires FROM USER_ACCOUNT WHERE reset_token = ?",
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        raise TokenError("Invalid or unknown reset token")

    user_id, email, expires_raw = row

    if expires_raw is None:
        raise TokenError("Invalid or unknown reset token")

    expires = _parse_datetime(expires_raw)
    # Guard: make expires timezone-aware if it's naive (older DB rows stored with utcnow())
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        raise TokenError("Reset token has expired")

    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    cursor.execute(
        """
        UPDATE USER_ACCOUNT
        SET password_hash = ?,
            reset_token = NULL,
            reset_token_expires = NULL,
            last_activity = ?
        WHERE id = ?
        """,
        (password_hash, datetime.now(timezone.utc), user_id),
    )
    conn.commit()

    return {"user_id": user_id, "email": email}
