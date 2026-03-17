"""
Database connection factory — supports SQLite (tests) and PostgreSQL (Supabase).
"""
import os
import sqlite3

def get_db_connection():
    """
    Returns a database connection.
    - If DB_TYPE=sqlite or no env var, returns sqlite3 in-memory (tests only).
    - Otherwise returns a psycopg2 connection using SUPABASE_CONNECTION_STRING env var.
    """
    db_type = os.environ.get('DB_TYPE', '').lower()
    if db_type == 'sqlite':
        return sqlite3.connect(os.environ.get('SQLITE_PATH', ':memory:'))

    import psycopg2
    from urllib.parse import urlparse, unquote
    db_url = os.environ.get('SUPABASE_CONNECTION_STRING')
    if not db_url:
        raise RuntimeError('SUPABASE_CONNECTION_STRING environment variable is required for PostgreSQL')
    # Parse manually — libpq truncates usernames containing dots (Supabase pooler issue)
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        dbname=(p.path or '/postgres').lstrip('/'),
        user=unquote(p.username or ''),
        password=unquote(p.password or ''),
        sslmode='require',
    )

def is_sqlite(conn):
    return isinstance(conn, sqlite3.Connection)

def placeholder(conn):
    """Return the correct parameterized query placeholder for this connection."""
    return '?' if is_sqlite(conn) else '%s'
