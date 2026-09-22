#!/usr/bin/env python3
"""
One-shot: seed meteo_grid table with current open-meteo data (352 points).

Usage (from repo root):
    source app_v2/.env && python functions/scripts/populate_meteo_grid.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.open_meteo_client import fetch_meteo_grid

url = os.environ.get("SUPABASE_CONNECTION_STRING", "")
if not url:
    print("SUPABASE_CONNECTION_STRING not set")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("pip install psycopg2-binary")
    sys.exit(1)

print("Fetching 352-point grid from open-meteo...")
rows = fetch_meteo_grid()
print(f"Got {len(rows)} points")

conn = psycopg2.connect(url, connect_timeout=15)
cur = conn.cursor()
psycopg2.extras.execute_values(
    cur,
    """
    INSERT INTO meteo_grid (lat, lon, cloud_cover, wind_speed, wind_direction, updated_at)
    VALUES %s
    ON CONFLICT (lat, lon) DO UPDATE SET
        cloud_cover    = EXCLUDED.cloud_cover,
        wind_speed     = EXCLUDED.wind_speed,
        wind_direction = EXCLUDED.wind_direction,
        updated_at     = now()
    """,
    [(r["lat"], r["lon"], r["cloud_cover"], r["wind_speed"], r["wind_direction"]) for r in rows],
)
conn.commit()
conn.close()
print(f"{len(rows)} rows upserted into meteo_grid")
