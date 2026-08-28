"""
Geocode production units seen in ENTSO-E generation-outage data — FT/GEODATA.

Standalone, on-demand script — deliberately NOT an Azure Function / pipeline
stage. Physical plant locations don't change on a schedule; this only needs
to run when a genuinely new unit name shows up in the outages feed that
isn't in the local cache yet.

Approach: pull real unit names from ENTSO-E (documentType A77 — see
functions/shared/entsoe_client.py), then resolve each one through OSM's
Nominatim search (nominatim.openstreetmap.org) — chosen over France's
official BAN address API (api-adresse.data.gouv.fr) after a real
side-by-side check on ambiguous names ("Rance", "Revin", "Hermillon",
"La Bâthie"): BAN is an *address* index and confidently returns unrelated
hamlets that happen to share the plant's name, with no way to tell from its
score alone (0.9+ on a wrong match is common) — hydro plants especially
share names with tiny villages all over France. Nominatim indexes OSM's
actual place/infrastructure graph and disambiguated all four correctly on
the first try. There is no single downloadable bulk registry with
per-installation coordinates (checked: the data.gouv.fr "registre national
des installations" mirrors resolve to ODRE's region-aggregated dataset,
which has no per-plant location at all) — this per-name lookup is the
practical alternative.

Nominatim's usage policy caps this at ~1 request/second and requires a
real User-Agent — respected here via NOMINATIM_DELAY_S. This is a script
run by hand a few times a year, not a service.

The cache (functions/shared/reference/production_unit_locations.json) is
merged, not overwritten: a later run only ever adds entries for unit names
it hasn't seen before. Anything already in the file — whether this script
resolved it automatically or a human hand-corrected it afterward — is left
exactly as-is, so fixing the handful of unresolved entries can happen
gradually, across sessions, without a re-run wiping out that work.

Usage:
    uv run python scripts/geocode_production_units.py
    uv run python scripts/geocode_production_units.py --days-back 180 --days-forward 180
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "functions"))

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "WATT_WATCHER-geodata-research/1.0 (personal portfolio project)"
NOMINATIM_DELAY_S = 1.1  # usage policy: max ~1 req/s

# Real infrastructure classes score above a plain administrative-boundary
# match (a commune centroid) when both are available for the same name.
_INFRA_CLASSES = {"power", "waterway", "water", "man_made"}

CACHE_PATH = Path(__file__).parent.parent / "functions" / "shared" / "reference" / "production_unit_locations.json"

_NOISE_PREFIXES = ("FR_", "BESS_")


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _nominatim_search(query: str) -> list[dict]:
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "countrycodes": "fr", "limit": 5},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("Nominatim request failed for %r: %s", query, exc)
        return []
    return resp.json()


def _candidate_queries(unit_name: str) -> list[str]:
    """
    Progressively simplified queries to try, most-specific first — except a
    trailing small integer ("SAINT AVOLD 7") goes *first* through the
    stripped version: Nominatim happily parses a trailing digit as a house
    number and confidently returns a wrong address elsewhere in France
    instead of reporting no match, so the noisy form must not be tried
    before the clean one for these.
    """
    no_trailing_number = re.sub(r"\s+\d+$", "", unit_name).strip()
    has_trailing_number = no_trailing_number != unit_name

    cleaned = unit_name
    for prefix in _NOISE_PREFIXES:
        cleaned = cleaned.replace(prefix, "")
    cleaned = cleaned.replace("_", " ").strip()

    candidates = [no_trailing_number] if has_trailing_number else [unit_name]
    if not has_trailing_number:
        candidates.append(no_trailing_number)
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)
    if has_trailing_number and unit_name not in candidates:
        candidates.append(unit_name)  # last resort — see docstring

    tokens = re.split(r"[\s_]+", cleaned)
    if len(tokens) > 1:
        candidates.append(tokens[-1])  # e.g. "BESS_AFD7_BARBAN_SAUCATS" -> "SAUCATS"

    seen = set()
    out = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _pick_best(results: list[dict]) -> dict | None:
    """Prefer an actual infrastructure feature (dam/plant/reservoir) over a
    plain administrative-boundary (commune centroid) match when both exist
    for the same query — otherwise take Nominatim's own top-ranked result."""
    if not results:
        return None
    for r in results:
        if r.get("class") in _INFRA_CLASSES:
            return r
    return results[0]


def geocode_unit(unit_name: str) -> dict:
    for query in _candidate_queries(unit_name):
        results = _nominatim_search(query)
        time.sleep(NOMINATIM_DELAY_S)
        best = _pick_best(results)
        if best:
            return {
                "lat": float(best["lat"]),
                "lon": float(best["lon"]),
                "label": best.get("display_name"),
                "class": best.get("class"),
                "type": best.get("type"),
                "query_used": query,
                "needs_review": False,
            }
    return {"lat": None, "lon": None, "label": None, "needs_review": True}


def fetch_known_unit_names(days_back: int, days_forward: int) -> set[str]:
    """Real unit names currently seen in the ENTSO-E outages feed."""
    from shared.entsoe_client import EntsoeClient

    token = os.environ.get("ENTSOE_API_TOKEN", "")
    if not token:
        raise SystemExit("ENTSOE_API_TOKEN not set — export it or load app_v2/.env first")

    client = EntsoeClient(api_token=token)
    now = datetime.now(timezone.utc)
    records = client.fetch_unavailability_of_production_units(
        now - timedelta(days=days_back), now + timedelta(days=days_forward),
    )
    return {r["unit_name"] for r in records}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--days-forward", type=int, default=90)
    args = parser.parse_args()

    cache = _load_cache()
    unit_names = fetch_known_unit_names(args.days_back, args.days_forward)
    new_names = sorted(n for n in unit_names if n not in cache)

    logger.info("%d unit names known, %d already cached, %d new to geocode",
                len(unit_names), len(unit_names) - len(new_names), len(new_names))

    for name in new_names:
        result = geocode_unit(name)
        cache[name] = result
        flag = "NEEDS REVIEW" if result["needs_review"] else "ok"
        logger.info("  [%s] %-40s -> %s", flag, name, result.get("label"))

    _save_cache(cache)

    needs_review = [n for n, v in cache.items() if v.get("needs_review")]
    logger.info("\nSaved %d entries to %s", len(cache), CACHE_PATH)
    logger.info("%d entries need manual review: %s", len(needs_review), ", ".join(needs_review))


if __name__ == "__main__":
    main()
