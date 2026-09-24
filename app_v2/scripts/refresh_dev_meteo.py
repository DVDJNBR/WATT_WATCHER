#!/usr/bin/env python3
"""
Bring dev.sqlite's FACT_METEO up to the present from Open-Meteo.

Why this exists: the seed copies Supabase wholesale, and upstream fact_meteo
trails fact_energy_flow by hours. The dashboard anchors its window on the
newest point *common* to every series (/v1/data-range), so a lagging météo
drags the whole dashboard back to a night-time cutoff where solar reads zero.
Filling the gap locally puts the window back on daylight hours.

Two deliberate differences from functions/shared/stages/meteo_stage.py:

  * timezone=UTC, not Europe/Paris. The pipeline requests Paris local time and
    stores it verbatim in a column whose other rows are UTC, which shifts météo
    ~2 h against production. Local fill stays in UTC so the two line up.
  * horodatage is written "YYYY-MM-DD HH:MM:00+00:00" to match every existing
    DIM_TIME row. The stage writes an ISO "T" form, which would leave the
    column in two formats and break the API's lexicographic range filters.

Usage:
    python scripts/refresh_dev_meteo.py [db_path]
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))
from shared.open_meteo_client import BASE_URL, REGION_CENTROIDS  # noqa: E402

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "dev.sqlite"
PAST_DAYS = 3
TS_FMT = "%Y-%m-%d %H:%M:00+00:00"


def fetch_region(code: str, info: dict) -> list[dict]:
    """Hourly UTC observations for one region centroid."""
    resp = requests.get(
        BASE_URL,
        params={
            "latitude": info["lat"],
            "longitude": info["lon"],
            "hourly": "temperature_2m,wind_speed_10m,cloudcover",
            "timezone": "UTC",
            "past_days": PAST_DAYS,
            # forecast_days=1 is what actually reaches today's hours. The
            # pipeline's 0 yields only *completed* past days, which is why
            # fact_meteo never holds the current day — the real source of the
            # "météo lags production" gap. Rows past the present hour are
            # dropped below, so nothing forecast-y lands in the table.
            "forecast_days": 1,
        },
        timeout=20,
    )
    resp.raise_for_status()
    hourly = resp.json().get("hourly", {})
    out = []
    for ts, temp, wind, cloud in zip(
        hourly.get("time", []),
        hourly.get("temperature_2m", []),
        hourly.get("wind_speed_10m", []),
        hourly.get("cloudcover", []),
    ):
        if temp is None:
            continue
        out.append({
            "code": code,
            # Open-Meteo hands back "YYYY-MM-DDTHH:MM"; re-render it in the
            # exact shape DIM_TIME already uses.
            "ts": datetime.strptime(ts, "%Y-%m-%dT%H:%M").strftime(TS_FMT),
            "temp": float(temp),
            "wind": float(wind) if wind is not None else None,
            "cloud": float(cloud) if cloud is not None else None,
        })
    return out


def main() -> int:
    if not DB_PATH.exists():
        print(f"✗ base introuvable : {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT MAX(t.horodatage) FROM FACT_METEO m JOIN DIM_TIME t ON m.id_date = t.id_date"
    )
    before = cur.fetchone()[0]
    print(f"météo actuelle jusqu'à : {before}")

    # Don't write observations dated in the future — Open-Meteo pads the
    # current hour forward and those rows would re-open the same gap.
    now_ts = datetime.now(timezone.utc).strftime(TS_FMT)

    cur.execute("SELECT code_insee, id_region FROM DIM_REGION")
    region_ids = {str(c): r for c, r in cur.fetchall()}

    cur.execute("SELECT horodatage, id_date FROM DIM_TIME")
    time_ids = {h: d for h, d in cur.fetchall()}

    cur.execute("SELECT MAX(id_date) FROM DIM_TIME")
    next_id_date = (cur.fetchone()[0] or 0) + 1
    cur.execute("SELECT MAX(id_fact) FROM FACT_METEO")
    next_id_fact = (cur.fetchone()[0] or 0) + 1

    # (id_date, id_region) already carrying météo — avoids duplicating rows
    # for hours the seed already brought in.
    cur.execute("SELECT id_date, id_region FROM FACT_METEO")
    existing = set(cur.fetchall())

    new_times, new_facts = [], []
    fetched = 0

    for code, info in REGION_CENTROIDS.items():
        id_region = region_ids.get(code)
        if id_region is None:
            print(f"  ⚠ région {code} absente de DIM_REGION, ignorée")
            continue
        try:
            rows = fetch_region(code, info)
        except Exception as exc:
            print(f"  ⚠ {code} {info['name']}: {exc}")
            continue
        fetched += len(rows)

        for r in rows:
            ts = r["ts"]
            if ts > now_ts:
                continue
            id_date = time_ids.get(ts)
            if id_date is None:
                id_date = next_id_date
                next_id_date += 1
                time_ids[ts] = id_date
                d = datetime.strptime(ts, TS_FMT)
                new_times.append((
                    id_date, ts, d.day, d.month, d.year, d.hour, d.minute,
                    d.weekday(), 1 if d.weekday() >= 5 else 0,
                ))
            if (id_date, id_region) in existing:
                continue
            existing.add((id_date, id_region))
            new_facts.append((
                next_id_fact, id_date, id_region, r["temp"], r["wind"], r["cloud"],
            ))
            next_id_fact += 1

    if new_times:
        cur.executemany(
            "INSERT INTO DIM_TIME (id_date, horodatage, jour, mois, annee, heure, "
            "minute, jour_semaine, est_weekend) VALUES (?,?,?,?,?,?,?,?,?)",
            new_times,
        )
    if new_facts:
        cur.executemany(
            "INSERT INTO FACT_METEO (id_fact, id_date, id_region, temperature_c, "
            "wind_speed_10m, cloudcover_pct) VALUES (?,?,?,?,?,?)",
            new_facts,
        )
    conn.commit()

    cur.execute(
        "SELECT MAX(t.horodatage) FROM FACT_METEO m JOIN DIM_TIME t ON m.id_date = t.id_date"
    )
    after = cur.fetchone()[0]
    conn.close()

    print(f"{fetched} points récupérés — {len(new_times)} DIM_TIME, {len(new_facts)} FACT_METEO insérés")
    print(f"météo désormais jusqu'à : {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
