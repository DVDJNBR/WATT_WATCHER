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

# Canvas map grid constants (must match SourcesCanvasMap.jsx)
_G_LON0, _G_LAT0 = -5.0, 41.0
_DLON,   _DLAT   = 0.75, 0.75
_G_NCOL, _G_NROW = 22, 16
_BATCH  = 100  # max locations per Open-Meteo request


def fetch_meteo_grid() -> list[dict]:
    """
    Fetch current cloud cover, wind speed and direction for the 22×16 grid
    covering metropolitan France (352 points, ~0.75° resolution).

    Uses Open-Meteo's multi-location support (comma-separated lat/lon).
    Returns list of {lat, lon, cloud_cover, wind_speed, wind_direction}.
    """
    # Build grid points
    points = [
        (round(_G_LAT0 + row * _DLAT, 4), round(_G_LON0 + col * _DLON, 4))
        for row in range(_G_NROW)
        for col in range(_G_NCOL)
    ]

    results: list[dict] = []

    for start in range(0, len(points), _BATCH):
        batch = points[start: start + _BATCH]
        lats = ",".join(str(p[0]) for p in batch)
        lons = ",".join(str(p[1]) for p in batch)
        try:
            resp = requests.get(
                BASE_URL,
                params={
                    "latitude":  lats,
                    "longitude": lons,
                    "current":   "cloudcover,wind_speed_10m,wind_direction_10m",
                    "timezone":  "UTC",
                    "forecast_days": 1,
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            # Single location → dict; multiple → list of dicts
            if isinstance(data, dict):
                data = [data]
            for item, (lat, lon) in zip(data, batch):
                cur = item.get("current", {})
                results.append({
                    "lat":           lat,
                    "lon":           lon,
                    "cloud_cover":   int(cur.get("cloudcover") or 0),
                    "wind_speed":    float(cur.get("wind_speed_10m") or 0.0),
                    "wind_direction": int(cur.get("wind_direction_10m") or 0),
                })
        except Exception as exc:
            logger.warning("fetch_meteo_grid batch %d failed: %s", start, exc)

    logger.info("fetch_meteo_grid: %d/%d points fetched", len(results), len(points))
    return results


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
