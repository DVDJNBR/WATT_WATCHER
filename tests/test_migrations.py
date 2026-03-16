"""Tests for SQL migration scripts — Story 1.1

Validates:
- Migration files exist and contain expected DDL
- Schema logic via SQLite-adapted equivalent (structural validation)
- Idempotency: running schema creation twice raises no error
- FK cascade relationships hold
- Unique deduplication constraint enforced
"""

import sqlite3
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "functions" / "migrations"


# ── File existence & content ────────────────────────────────────────────────

def test_migration_files_exist():
    assert (MIGRATIONS_DIR / "001_create_user_account.sql").exists()
    assert (MIGRATIONS_DIR / "002_create_alert_subscription.sql").exists()
    assert (MIGRATIONS_DIR / "003_create_alert_sent_log.sql").exists()


def _read(filename: str) -> str:
    return (MIGRATIONS_DIR / filename).read_text()


def test_001_contains_user_account_table():
    sql = _read("001_create_user_account.sql")
    assert "USER_ACCOUNT" in sql
    assert "email" in sql
    assert "password_hash" in sql
    assert "is_confirmed" in sql
    assert "confirmation_token" in sql
    assert "reset_token" in sql
    assert "reset_token_expires" in sql
    assert "last_activity" in sql
    assert "created_at" in sql


def test_001_contains_email_index():
    sql = _read("001_create_user_account.sql")
    assert "IX_USER_ACCOUNT_email" in sql


def test_001_is_idempotent_pattern():
    sql = _read("001_create_user_account.sql")
    assert "IF NOT EXISTS" in sql


def test_002_contains_alert_subscription_table():
    sql = _read("002_create_alert_subscription.sql")
    assert "ALERT_SUBSCRIPTION" in sql
    assert "user_id" in sql
    assert "region_code" in sql
    assert "alert_type" in sql
    assert "is_active" in sql
    assert "ON DELETE CASCADE" in sql


def test_002_contains_user_region_composite_index():
    """Index must be composite (user_id, region_code) to support WHERE user_id=? AND region_code=? queries."""
    sql = _read("002_create_alert_subscription.sql")
    assert "IX_ALERT_SUBSCRIPTION_user_region" in sql
    # Verify both columns appear in the index definition (after the index name)
    idx = sql.index("IX_ALERT_SUBSCRIPTION_user_region")
    index_def = sql[idx:]
    assert "user_id" in index_def
    assert "region_code" in index_def


def test_002_is_idempotent_pattern():
    sql = _read("002_create_alert_subscription.sql")
    assert "IF NOT EXISTS" in sql


def test_003_contains_alert_sent_log_table():
    sql = _read("003_create_alert_sent_log.sql")
    assert "ALERT_SENT_LOG" in sql
    assert "user_id" in sql
    assert "region_code" in sql
    assert "alert_type" in sql
    assert "sent_at" in sql
    assert "ON DELETE CASCADE" in sql


def test_003_contains_deduplication_unique_index():
    sql = _read("003_create_alert_sent_log.sql")
    assert "UQ_ALERT_SENT_LOG_daily" in sql
    assert "UNIQUE" in sql


def test_003_is_idempotent_pattern():
    sql = _read("003_create_alert_sent_log.sql")
    assert "IF NOT EXISTS" in sql


# ── Schema logic via SQLite (structural validation) ─────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite with the three auth tables (SQLite-adapted schema)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS USER_ACCOUNT (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            email               TEXT    NOT NULL UNIQUE,
            password_hash       TEXT    NOT NULL,
            is_confirmed        INTEGER NOT NULL DEFAULT 0,
            confirmation_token  TEXT    NULL,
            reset_token         TEXT    NULL,
            reset_token_expires TEXT    NULL,
            last_activity       TEXT    NOT NULL DEFAULT (datetime('now')),
            created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ALERT_SUBSCRIPTION (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT    NOT NULL,
            alert_type  TEXT    NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ALERT_SENT_LOG (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
            region_code TEXT    NOT NULL,
            alert_type  TEXT    NOT NULL,
            sent_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS IX_ALERT_SUBSCRIPTION_user_region
        ON ALERT_SUBSCRIPTION (user_id, region_code);

        -- Note: SQL Server uses CAST(sent_at AS DATE); SQLite uses date(sent_at).
        -- Both produce equivalent deduplication behaviour — syntax differs by engine.
        CREATE UNIQUE INDEX IF NOT EXISTS UQ_ALERT_SENT_LOG_daily
        ON ALERT_SENT_LOG (user_id, region_code, alert_type, date(sent_at));
    """)
    conn.commit()
    yield conn
    conn.close()


def test_user_account_table_created(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='USER_ACCOUNT'"
    )
    assert cursor.fetchone() is not None


def test_alert_subscription_table_created(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ALERT_SUBSCRIPTION'"
    )
    assert cursor.fetchone() is not None


def test_alert_sent_log_table_created(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ALERT_SENT_LOG'"
    )
    assert cursor.fetchone() is not None


def test_schema_idempotent(db):
    """Running CREATE TABLE IF NOT EXISTS twice raises no error."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmation_token TEXT NULL,
            reset_token TEXT NULL,
            reset_token_expires TEXT NULL,
            last_activity TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    db.commit()


def test_fk_cascade_delete_subscription(db):
    """Deleting a USER_ACCOUNT cascades to ALERT_SUBSCRIPTION."""
    db.execute(
        "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
        ("alice@example.com", "hashed"),
    )
    db.commit()
    user_id = db.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email='alice@example.com'"
    ).fetchone()[0]

    db.execute(
        "INSERT INTO ALERT_SUBSCRIPTION (user_id, region_code, alert_type) VALUES (?, ?, ?)",
        (user_id, "11", "under_production"),
    )
    db.commit()

    db.execute("DELETE FROM USER_ACCOUNT WHERE id=?", (user_id,))
    db.commit()

    rows = db.execute(
        "SELECT * FROM ALERT_SUBSCRIPTION WHERE user_id=?", (user_id,)
    ).fetchall()
    assert rows == [], "Subscriptions should be deleted when user is deleted"


def test_fk_cascade_delete_sent_log(db):
    """Deleting a USER_ACCOUNT cascades to ALERT_SENT_LOG."""
    db.execute(
        "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
        ("bob@example.com", "hashed"),
    )
    db.commit()
    user_id = db.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email='bob@example.com'"
    ).fetchone()[0]

    db.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) VALUES (?, ?, ?, ?)",
        (user_id, "11", "over_production", "2026-03-09 10:00:00"),
    )
    db.commit()

    db.execute("DELETE FROM USER_ACCOUNT WHERE id=?", (user_id,))
    db.commit()

    rows = db.execute(
        "SELECT * FROM ALERT_SENT_LOG WHERE user_id=?", (user_id,)
    ).fetchall()
    assert rows == [], "Alert logs should be deleted when user is deleted"


def test_deduplication_unique_constraint(db):
    """Cannot insert two ALERT_SENT_LOG rows for same user/region/type/day."""
    db.execute(
        "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
        ("carol@example.com", "hashed"),
    )
    db.commit()
    user_id = db.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email='carol@example.com'"
    ).fetchone()[0]

    db.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) VALUES (?, ?, ?, ?)",
        (user_id, "11", "under_production", "2026-03-09 08:00:00"),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) VALUES (?, ?, ?, ?)",
            (user_id, "11", "under_production", "2026-03-09 14:00:00"),
        )
        db.commit()


def test_deduplication_allows_different_day(db):
    """Two ALERT_SENT_LOG rows for same user/region/type but different days are allowed."""
    db.execute(
        "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
        ("dave@example.com", "hashed"),
    )
    db.commit()
    user_id = db.execute(
        "SELECT id FROM USER_ACCOUNT WHERE email='dave@example.com'"
    ).fetchone()[0]

    db.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) VALUES (?, ?, ?, ?)",
        (user_id, "11", "under_production", "2026-03-09 08:00:00"),
    )
    db.execute(
        "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type, sent_at) VALUES (?, ?, ?, ?)",
        (user_id, "11", "under_production", "2026-03-10 08:00:00"),
    )
    db.commit()

    count = db.execute(
        "SELECT COUNT(*) FROM ALERT_SENT_LOG WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    assert count == 2


def test_user_account_email_unique(db):
    """USER_ACCOUNT email must be unique."""
    db.execute(
        "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
        ("unique@example.com", "hashed"),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO USER_ACCOUNT (email, password_hash) VALUES (?, ?)",
            ("unique@example.com", "other_hash"),
        )
        db.commit()
