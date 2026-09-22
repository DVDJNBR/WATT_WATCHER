"""
Supabase REST client (PostgREST) — upsert helper.
Uses requests + service_role key; no supabase-py dependency needed.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def upsert(table: str, rows: list[dict], on_conflict: str) -> None:
    """
    Upsert rows into a Supabase table via PostgREST.

    Args:
        table:       Table name (e.g. "meteo_grid").
        rows:        List of dicts matching table columns.
        on_conflict: Comma-separated PK column(s) for merge resolution
                     (e.g. "lat,lon").
    """
    if not rows:
        return
    if not _SUPABASE_URL or not _SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")

    url = f"{_SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey":        _SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        f"resolution=merge-duplicates,return=minimal",
    }
    resp = requests.post(url, json=rows, headers=headers, timeout=30)
    resp.raise_for_status()
    logger.info("upsert %s: %d rows → HTTP %d", table, len(rows), resp.status_code)
