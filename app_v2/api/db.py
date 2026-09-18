"""
Database connection factory — Supabase (PostgreSQL) in production, SQLite for tests.
"""
import os
import sqlite3
import threading

_pg_pool = None
_pg_pool_lock = threading.Lock()


class _PooledConnection:
    """
    Thin proxy around a pooled psycopg2 connection.

    psycopg2 connection objects are a C extension type — their attributes
    (including `close`) are read-only, so it can't be monkeypatched onto the
    instance directly (confirmed: raises AttributeError). This wrapper
    delegates everything to the real connection except close(), which
    returns the connection to the pool instead of tearing down the socket.
    """

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def close(self):
        try:
            self._conn.rollback()
            self._pool.putconn(self._conn)
        except Exception:
            self._pool.putconn(self._conn, close=True)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _get_pg_pool():
    """
    Lazily create a process-wide connection pool.

    Every request used to open a brand-new psycopg2.connect() — a fresh
    TCP+TLS handshake to Supabase's remote pooler each time (~1s, confirmed
    by direct benchmarking: 9 requests fired in parallel still took ~9s
    wall-clock, i.e. no real concurrency, because the bottleneck was
    connection setup, not the query). A small pool amortizes that handshake
    cost across requests instead of paying it every time.
    """
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                from psycopg2.pool import ThreadedConnectionPool
                from urllib.parse import urlparse, unquote

                db_url = os.environ.get("SUPABASE_CONNECTION_STRING")
                if not db_url:
                    raise RuntimeError("SUPABASE_CONNECTION_STRING environment variable is required")

                # Parse manually — libpq truncates usernames containing dots (Supabase pooler issue)
                p = urlparse(db_url)
                _pg_pool = ThreadedConnectionPool(
                    1, 10,
                    host=p.hostname,
                    port=p.port or 5432,
                    dbname=(p.path or "/postgres").lstrip("/"),
                    user=unquote(p.username or ""),
                    password=unquote(p.password or ""),
                    sslmode="require",
                )
    return _pg_pool


def get_db_connection():
    """
    Returns a database connection.
    - DB_TYPE=sqlite (or SQLITE_PATH set) → sqlite3 (tests / local dev).
    - Otherwise → a pooled psycopg2 connection to Supabase.

    Callers close() the connection when done, same as before — that call is
    transparently rewired below to return the connection to the pool rather
    than tearing down the socket, so no call site needs to change.
    """
    db_type = os.environ.get("DB_TYPE", "").lower()
    if db_type == "sqlite":
        return sqlite3.connect(os.environ.get("SQLITE_PATH", ":memory:"))

    pool = _get_pg_pool()
    return _PooledConnection(pool.getconn(), pool)


def is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def placeholder(conn) -> str:
    """Return the correct parameterized query placeholder for this connection."""
    return "?" if is_sqlite(conn) else "%s"
