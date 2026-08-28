"""Gold SQL DB connection helper — shared by function_app.py and every pipeline stage."""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def get_db_connection() -> Any:
    """
    Return a Gold SQL DB connection.

    Priority:
    1. SUPABASE_CONNECTION_STRING env var -> psycopg2 (Supabase/PostgreSQL in production)
    2. LOCAL_GOLD_DB env var -> sqlite3 (local dev, points to gold.db path)
    3. Default -> sqlite3 on gold.db in project root (local dev fallback)
    """
    db_url = os.environ.get("SUPABASE_CONNECTION_STRING", "")
    if db_url:
        try:
            import psycopg2  # type: ignore[import]
            from urllib.parse import urlparse, unquote
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
        except ImportError as e:
            raise RuntimeError("psycopg2 not available — install psycopg2-binary") from e

    # Local dev fallback: sqlite3
    import sqlite3
    from pathlib import Path
    local_db = os.environ.get(
        "LOCAL_GOLD_DB",
        str(Path(__file__).parent.parent.parent / "gold.db"),
    )
    logger.info("SUPABASE_CONNECTION_STRING not set — using local SQLite: %s", local_db)
    return sqlite3.connect(local_db)
