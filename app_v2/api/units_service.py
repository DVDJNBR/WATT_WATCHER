"""
Units Service — large production unit locations (nuclear plants, wind farms,
dams, ...) for the map's source pictograms.

Static reference data (functions/shared/reference/production_unit_locations.json,
built by scripts/geocode_production_units.py), not a DB query — the file is
read once and cached in memory for the process lifetime.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Docker image copies the file to ./reference/ (see api/Dockerfile); local
# dev (uvicorn run straight from the app_v2/ source tree) has it at its
# original path under functions/. Try both rather than assuming one layout.
_CANDIDATE_PATHS = [
    Path(__file__).parent.parent / "reference" / "production_unit_locations.json",
    Path(__file__).parent.parent / "functions" / "shared" / "reference" / "production_unit_locations.json",
]

# The geocoder (Nominatim, free-text name search) occasionally resolves a
# unit to a same-named place with no relation to the real plant — e.g. a
# Brittany offshore wind farm landing in French Polynesia because its name
# matched a museum there. There's no per-entry confidence score to filter
# on, but every genuine mainland French address ends up with one of these
# 13 région names somewhere in its Nominatim label — so matching against
# that list doubles as a correctness filter and a way to group pins by
# région without needing real polygon/point-in-region geometry.
REGIONS = [
    "Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne",
    "Centre-Val de Loire", "Corse", "Grand Est", "Hauts-de-France",
    "Île-de-France", "Normandie", "Nouvelle-Aquitaine", "Occitanie",
    "Pays de la Loire", "Provence-Alpes-Côte d'Azur",
]


def _load_raw() -> dict:
    for path in _CANDIDATE_PATHS:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    logger.warning("production_unit_locations.json not found in any candidate path")
    return {}


@lru_cache(maxsize=1)
def _load_units() -> list[dict]:
    raw = _load_raw()
    units = []
    for name, entry in raw.items():
        lat, lon = entry.get("lat"), entry.get("lon")
        psr_type = entry.get("psr_type")
        label = entry.get("label", "")
        if lat is None or lon is None or not psr_type:
            continue
        region = next((r for r in REGIONS if r in label), None)
        if region is None:
            continue  # geocode landed outside metropolitan France (or unresolvable) — drop it
        units.append({
            "name": name.title(),
            "lat": lat,
            "lon": lon,
            "psr_type": psr_type,
            "region": region,
        })
    return units


def query_units(region: Optional[str] = None) -> dict:
    units = _load_units()
    if region:
        units = [u for u in units if u["region"] == region]
    return {"data": units, "total_records": len(units)}
