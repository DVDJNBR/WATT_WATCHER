"""
Open-Meteo Client — météo data for French regions.

Free API, no authentication required.
https://open-meteo.com/
"""

import logging

import requests

logger = logging.getLogger(__name__)

# French region centroids: code_insee → {lat, lon, name}
REGION_CENTROIDS = {
    "11": {"name": "Île-de-France",             "lat": 48.85, "lon": 2.35},
    "24": {"name": "Centre-Val de Loire",        "lat": 47.75, "lon": 1.67},
    "27": {"name": "Bourgogne-Franche-Comté",    "lat": 47.28, "lon": 5.99},
    "28": {"name": "Normandie",                  "lat": 49.18, "lon": 0.37},
    "32": {"name": "Hauts-de-France",            "lat": 50.48, "lon": 2.79},
    "44": {"name": "Grand Est",                  "lat": 48.68, "lon": 6.18},
    "52": {"name": "Pays de la Loire",           "lat": 47.76, "lon": -0.33},
    "53": {"name": "Bretagne",                   "lat": 48.20, "lon": -2.93},
    "75": {"name": "Nouvelle-Aquitaine",         "lat": 44.85, "lon": 0.74},
    "76": {"name": "Occitanie",                  "lat": 43.89, "lon": 2.40},
    "84": {"name": "Auvergne-Rhône-Alpes",       "lat": 45.75, "lon": 4.84},
    "93": {"name": "Provence-Alpes-Côte d'Azur", "lat": 43.94, "lon": 6.06},
    "94": {"name": "Corse",                      "lat": 42.03, "lon": 9.01},
}

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Grille 22×16 couvrant la France (même params que maquette JS)
GRID_LON0, GRID_LAT0 = -5.0, 41.0
GRID_DLON, GRID_DLAT = 0.75, 0.75
GRID_NCOL, GRID_NROW = 22, 16


def fetch_meteo_grid() -> list[dict]:
    """
    Fetch current cloud_cover, wind_speed_10m, wind_direction_10m
    for the 22×16 = 352-point grid covering France.

    Single batch request to open-meteo multi-location API.
    Returns list[{lat, lon, cloud_cover, wind_speed, wind_direction}].
    """
    lats, lons = [], []
    for ri in range(GRID_NROW):
        for ci in range(GRID_NCOL):
            lats.append(round(GRID_LAT0 + ri * GRID_DLAT, 2))
            lons.append(round(GRID_LON0 + ci * GRID_DLON, 2))

    resp = requests.get(
        BASE_URL,
        params={
            "latitude":  ",".join(str(v) for v in lats),
            "longitude": ",".join(str(v) for v in lons),
            "current":   "cloud_cover,wind_speed_10m,wind_direction_10m",
            "timezone":  "UTC",
            "forecast_days": 1,
        },
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json()
    if not isinstance(results, list):
        results = [results]

    records = []
    for i, pt in enumerate(results):
        cur = pt.get("current") or {}
        records.append({
            "lat":           lats[i],
            "lon":           lons[i],
            "cloud_cover":   int(cur.get("cloud_cover") or 0),
            "wind_speed":    float(cur.get("wind_speed_10m") or 0.0),
            "wind_direction": int(cur.get("wind_direction_10m") or 0),
        })

    logger.info("fetch_meteo_grid: %d points fetched", len(records))
    return records


def fetch_meteo_all_regions(past_days: int = 3) -> list[dict]:
    """
    Fetch hourly temperature, wind speed, and cloud cover for all French regions.

    Args:
        past_days: Number of past days to retrieve (0–7 on free tier).

    Returns:
        List of dicts: {region_code, region_name, timestamp, temperature_c,
                        wind_speed_10m, cloudcover_pct}
    """
    records = []

    for code, info in REGION_CENTROIDS.items():
        try:
            resp = requests.get(
                BASE_URL,
                params={
                    "latitude": info["lat"],
                    "longitude": info["lon"],
                    "hourly": "temperature_2m,wind_speed_10m,cloudcover",
                    "timezone": "Europe/Paris",
                    "past_days": past_days,
                    "forecast_days": 0,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            hourly = data.get("hourly", {})
            times  = hourly.get("time", [])
            temps  = hourly.get("temperature_2m", [])
            winds  = hourly.get("wind_speed_10m", [])
            clouds = hourly.get("cloudcover", [])

            for ts, temp, wind, cloud in zip(times, temps, winds, clouds):
                if temp is not None:
                    records.append({
                        "region_code": code,
                        "region_name": info["name"],
                        "timestamp": ts,          # "YYYY-MM-DDTHH:MM"
                        "temperature_c":  float(temp),
                        "wind_speed_10m": float(wind)  if wind  is not None else None,
                        "cloudcover_pct": float(cloud) if cloud is not None else None,
                    })

            logger.info("Fetched %d météo records for region %s (%s) (cloudcover included)", len(times), code, info["name"])

        except Exception as exc:
            logger.warning("Failed to fetch météo for region %s: %s", code, exc)

    logger.info("Total météo records fetched: %d", len(records))
    return records
