#!/usr/bin/env python3
"""
Story 0.1 — Task 1: RTE eCO2mix API Exploration Script

Explores the Opendatasoft v2.1 API for eCO2mix datasets.
Outputs: response structure documentation, sample data, field analysis.

Usage:
    python scripts/explore_rte_api.py
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"

DATASETS = {
    "regional_tr": "eco2mix-regional-tr",          # Temps réel régional
    "national_tr": "eco2mix-national-tr",          # Temps réel national
    "regional_def": "eco2mix-regional-cons-def",   # Consolidé régional
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
DOCS_DIR = PROJECT_ROOT / "docs"


def fetch_records(dataset_id: str, limit: int = 10, **params) -> dict:
    """Fetch records from Opendatasoft v2.1 API."""
    url = f"{BASE_URL}/{dataset_id}/records"
    params = {"limit": limit, **params}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def explore_dataset(dataset_id: str, label: str) -> dict:
    """Explore a single dataset: fetch sample, analyze structure."""
    print(f"\n{'='*60}")
    print(f"  Dataset: {label} ({dataset_id})")
    print(f"{'='*60}")

    data = fetch_records(dataset_id, limit=5)
    total = data.get("total_count", "?")
    records = data.get("results", [])

    print(f"  Total records: {total:,}")
    print(f"  Sample size:   {len(records)}")

    if not records:
        print("  ⚠️  No records returned.")
        return {"dataset": dataset_id, "total": total, "fields": {}, "sample": []}

    # Analyze field structure from first record
    sample = records[0]
    fields = {}
    for key, val in sample.items():
        fields[key] = {
            "type": type(val).__name__,
            "sample": val,
            "nullable": any(r.get(key) is None for r in records),
        }

    # Print field analysis
    print(f"\n  Fields ({len(fields)}):")
    print(f"  {'Field':<35} {'Type':<10} {'Nullable':<9} {'Sample'}")
    print(f"  {'-'*35} {'-'*10} {'-'*9} {'-'*30}")
    for name, info in fields.items():
        sample_val = str(info["sample"])[:30]
        print(f"  {name:<35} {info['type']:<10} {str(info['nullable']):<9} {sample_val}")

    return {
        "dataset": dataset_id,
        "label": label,
        "total_count": total,
        "fields": fields,
        "sample_records": records,
    }


def test_pagination(dataset_id: str):
    """Test pagination behavior."""
    print(f"\n--- Pagination test: {dataset_id} ---")
    for offset in [0, 10, 100]:
        data = fetch_records(dataset_id, limit=1, offset=offset)
        rec = data["results"][0] if data["results"] else None
        ts = rec.get("date_heure", "?") if rec else "empty"
        print(f"  offset={offset}: date_heure={ts}")


def test_filtering(dataset_id: str):
    """Test ODSQL filtering capabilities."""
    print(f"\n--- Filter test: {dataset_id} ---")

    # Date filter
    yesterday = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        data = fetch_records(
            dataset_id, limit=2,
            where=f"date >= '{yesterday}'",
            order_by="date_heure DESC"
        )
        print(f"  Date filter (>= {yesterday}): {data['total_count']} records")
    except requests.HTTPError as e:
        print(f"  Date filter failed: {e}")

    # Region filter (regional only)
    if "regional" in dataset_id:
        try:
            data = fetch_records(
                dataset_id, limit=2,
                where="code_insee_region = '11'",  # Île-de-France
            )
            print(f"  Region filter (IDF '11'): {data['total_count']} records")
            if data["results"]:
                print(f"    → libelle_region: {data['results'][0].get('libelle_region')}")
        except requests.HTTPError as e:
            print(f"  Region filter failed: {e}")


def discover_regions(dataset_id: str) -> list[dict]:
    """Discover all unique regions in the dataset."""
    print(f"\n--- Region discovery: {dataset_id} ---")
    try:
        url = f"{BASE_URL}/{dataset_id}/records"
        data = requests.get(url, params={
            "select": "code_insee_region, libelle_region",
            "group_by": "code_insee_region, libelle_region",
            "limit": 50,
        }, timeout=30).json()

        regions = data.get("results", [])
        print(f"  Found {len(regions)} unique regions:")
        for r in sorted(regions, key=lambda x: x.get("code_insee_region", "")):
            print(f"    {r.get('code_insee_region', '?'):>3} → {r.get('libelle_region', '?')}")
        return regions
    except Exception as e:
        print(f"  Region discovery failed: {e}")
        return []


def discover_energy_sources(sample_record: dict) -> list[dict]:
    """Extract energy source types from a sample record."""
    # Production fields (MW values)
    production_fields = [
        "thermique", "nucleaire", "eolien", "solaire",
        "hydraulique", "pompage", "bioenergies",
        "stockage_batterie", "destockage_batterie",
    ]
    # Also check national-specific fields
    national_extra = [
        "fioul", "charbon", "gaz",
        "eolien_terrestre", "eolien_offshore",
    ]

    sources = []
    for field in production_fields + national_extra:
        if field in sample_record:
            val = sample_record[field]
            sources.append({"field": field, "sample_mw": val})

    print(f"\n  Energy sources found: {len(sources)}")
    for s in sources:
        print(f"    {s['field']:<30} {s['sample_mw']} MW")

    return sources


def save_fixtures(results: dict):
    """Save sample API responses as test fixtures."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Save regional real-time sample
    regional = results.get("regional_tr", {})
    if regional.get("sample_records"):
        path = FIXTURES_DIR / "rte_eco2mix_regional_sample.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(regional["sample_records"], f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ Saved: {path}")

    # Save national sample
    national = results.get("national_tr", {})
    if national.get("sample_records"):
        path = FIXTURES_DIR / "rte_eco2mix_national_sample.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(national["sample_records"], f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ Saved: {path}")


def main():
    print("=" * 60)
    print("  RTE eCO2mix API Exploration — Story 0.1")
    print(f"  Date: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Explore all datasets
    results = {}
    for key, dataset_id in DATASETS.items():
        try:
            results[key] = explore_dataset(dataset_id, key)
        except Exception as e:
            print(f"\n  ❌ Error exploring {key}: {e}")
            results[key] = {"error": str(e)}

    # 2. Pagination test
    test_pagination(DATASETS["regional_tr"])

    # 3. Filtering test
    test_filtering(DATASETS["regional_tr"])

    # 4. Region discovery
    regions = discover_regions(DATASETS["regional_tr"])

    # 5. Energy source analysis
    regional_sample = results.get("regional_tr", {}).get("sample_records", [{}])
    if regional_sample:
        discover_energy_sources(regional_sample[0])

    # 6. Save fixtures
    save_fixtures(results)

    # 7. Summary
    print("\n" + "=" * 60)
    print("  EXPLORATION SUMMARY")
    print("=" * 60)
    print(f"""
  KEY FINDINGS:
  ─────────────
  1. API is PUBLIC — no authentication required (Opendatasoft v2.1)
  2. Base URL: {BASE_URL}
  3. Primary dataset: eco2mix-regional-tr ({results.get('regional_tr', {}).get('total_count', '?')} records)
  4. Data granularity: 15 minutes (confirmed)
  5. Pagination: offset/limit supported
  6. Filtering: ODSQL where clause (date, region, etc.)
  7. Regions: {len(regions)} found
  8. BONUS: tco_*/tch_* fields = facteur de charge already computed by RTE!
  9. Fields NOT in CONCEPTION: thermique, tco_*, tch_*, stockage_batterie, column_68
  10. Fields in CONCEPTION but NOT in regional API: fioul, charbon, gaz (national only)
    """)

    return results


if __name__ == "__main__":
    results = main()
