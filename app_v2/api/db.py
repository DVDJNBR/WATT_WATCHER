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


_PG_POOL_MAX = 10


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
                    1, _PG_POOL_MAX,
                    host=p.hostname,
                    port=p.port or 5432,
                    dbname=(p.path or "/postgres").lstrip("/"),
                    user=unquote(p.username or ""),
                    password=unquote(p.password or ""),
                    sslmode="require",
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                )
    return _pg_pool


def get_db_connection():
    """
    Returns a database connection.
    - DB_TYPE=sqlite (or SQLITE_PATH set) → sqlite3 (tests / local dev).
    - Otherwise → a pooled psycopg2 connection to Supabase.

    Validates each connection before returning — stale connections (closed by
    Supabase idle timeout) are evicted from the pool and a fresh one is used.
    """
    db_type = os.environ.get("DB_TYPE", "").lower()
    if db_type == "sqlite":
        return sqlite3.connect(os.environ.get("SQLITE_PATH", ":memory:"))

    import psycopg2

    pool = _get_pg_pool()
    # After a long idle spell every pooled connection can be dead, so allow
    # one attempt per pool slot plus a fresh one.
    for _attempt in range(_PG_POOL_MAX + 1):
        raw = pool.getconn()
        if raw.closed:
            pool.putconn(raw, close=True)
            continue
        # `closed` only reflects a close on our side. A connection the server
        # dropped while idle (Neon closes them after a few minutes) still
        # reads as open and fails on first use with "SSL connection has been
        # closed unexpectedly" — a 500 for whoever drew it. Ping it first.
        try:
            with raw.cursor() as cur:
                cur.execute("SELECT 1")
            raw.rollback()
        except psycopg2.Error:
            pool.putconn(raw, close=True)
            continue
        return _PooledConnection(raw, pool)
    raise RuntimeError(
        f"Could not obtain a live database connection after {_PG_POOL_MAX + 1} attempts"
    )


def is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def placeholder(conn) -> str:
    """Return the correct parameterized query placeholder for this connection."""
    return "?" if is_sqlite(conn) else "%s"
