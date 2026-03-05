"""Tests for Gold layer (dim_loader + fact_loader) — Story 3.2, Task 5"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from functions.shared.gold.dim_loader import DimLoader
from functions.shared.gold.fact_loader import FactLoader


@pytest.fixture
def db():
    """In-memory SQLite with Gold Star Schema."""
    conn = sqlite3.connect(":memory:")
    dim = DimLoader(conn)
    dim.ensure_schema()
    return conn


@pytest.fixture
def dim(db):
    return DimLoader(db)


@pytest.fixture
def silver_parquet(tmp_path):
    """Create a Silver Parquet fixture for Gold loading."""
    df = pd.DataFrame([
        {
            "code_insee_region": "11",
            "libelle_region": "Île-de-France",
            "date_heure": "2025-06-15T10:00:00+00:00",
            "nucleaire_mw": 3200.0,
            "eolien_mw": 450.0,
            "solaire_mw": 320.0,
            "hydraulique_mw": 180.0,
            "gaz_mw": 120.0,
            "charbon_mw": 0.0,
            "fioul_mw": 0.0,
            "bioenergies_mw": 45.0,
        },
        {
            "code_insee_region": "84",
            "libelle_region": "Auvergne-Rhône-Alpes",
            "date_heure": "2025-06-15T10:00:00+00:00",
            "nucleaire_mw": 2100.0,
            "eolien_mw": 280.0,
            "solaire_mw": 510.0,
            "hydraulique_mw": 890.0,
            "gaz_mw": 0.0,
            "charbon_mw": 0.0,
            "fioul_mw": 0.0,
            "bioenergies_mw": 30.0,
        },
    ])
    path = tmp_path / "silver.parquet"
    df.to_parquet(path, index=False)
    return path


# ─── DIM Loader Tests ────────────────────────────────────────────────────────

class TestDimLoader:
    def test_upsert_regions(self, dim):
        """AC #3: Regions are inserted."""
        count = dim.upsert_regions([
            {"code_insee": "11", "nom_region": "Île-de-France"},
            {"code_insee": "84", "nom_region": "Auvergne-Rhône-Alpes"},
        ])
        assert count == 2
        assert dim.get_region_id("11") is not None

    def test_upsert_regions_idempotent(self, dim):
        """AC #3: Upsert is idempotent — re-run doesn't duplicate."""
        dim.upsert_regions([{"code_insee": "11", "nom_region": "IDF"}])
        dim.upsert_regions([{"code_insee": "11", "nom_region": "Île-de-France"}])
        cursor = dim.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM DIM_REGION WHERE code_insee = '11'")
        assert cursor.fetchone()[0] == 1

    def test_upsert_time(self, dim):
        count = dim.upsert_time(["2025-06-15T10:00:00+00:00"])
        assert count == 1
        assert dim.get_time_id("2025-06-15T10:00:00+00:00") is not None

    def test_upsert_sources(self, dim):
        count = dim.upsert_sources()
        assert count == 8  # 8 default French energy sources
        assert dim.get_source_id("nucleaire") is not None
        assert dim.get_source_id("eolien") is not None

    def test_weekend_detection(self, dim):
        """DIM_TIME correctly flags weekends."""
        dim.upsert_time(["2025-06-15T10:00:00+00:00"])  # Sunday
        cursor = dim.conn.cursor()
        cursor.execute("SELECT est_weekend FROM DIM_TIME WHERE horodatage = '2025-06-15T10:00:00+00:00'")
        assert cursor.fetchone()[0] == 1

    def test_upsert_time_skips_invalid_timestamps(self, dim):
        """Malformed timestamps are silently skipped, valid ones still inserted."""
        count = dim.upsert_time([
            "not-a-date",
            "2025-06-15T10:00:00+00:00",  # valid
            "",
            None,
            "9999-99-99T99:99:99",
        ])
        # Only the valid timestamp is inserted
        assert count == 1
        assert dim.get_time_id("2025-06-15T10:00:00+00:00") is not None

    def test_upsert_time_all_invalid_returns_zero(self, dim):
        """All invalid timestamps → returns 0 without raising."""
        count = dim.upsert_time(["garbage", "also-garbage"])
        assert count == 0

    def test_upsert_time_empty_list(self, dim):
        """Empty list → returns 0."""
        count = dim.upsert_time([])
        assert count == 0

    def test_upsert_regions_empty_list(self, dim):
        """Empty regions list → returns 0 without error."""
        count = dim.upsert_regions([])
        assert count == 0


# ─── Fact Loader Tests ───────────────────────────────────────────────────────

class TestFactLoader:
    def test_load_silver(self, db, silver_parquet):
        """AC #1, #2: Silver Parquet → FACT_ENERGY_FLOW."""
        loader = FactLoader(db)
        result = loader.load_from_silver(silver_parquet)
        assert result["status"] == "success"
        assert result["rows_loaded"] > 0

    def test_fact_count(self, db, silver_parquet):
        """Multiple sources per region per time → correct fact count."""
        loader = FactLoader(db)
        loader.load_from_silver(silver_parquet)
        # 2 regions × 8 source columns (some 0) = up to 16 rows
        count = loader.get_fact_count()
        assert count > 0

    def test_facteur_charge(self, db, silver_parquet):
        """Load factor calculated when capacity data provided."""
        capacity = {"nucleaire": 10000.0, "eolien": 2000.0}
        loader = FactLoader(db, capacity_data=capacity)
        loader.load_from_silver(silver_parquet)

        cursor = db.cursor()
        cursor.execute(
            """SELECT f.facteur_charge
               FROM FACT_ENERGY_FLOW f
               JOIN DIM_SOURCE s ON f.id_source = s.id_source
               WHERE s.source_name = 'nucleaire' AND f.facteur_charge IS NOT NULL"""
        )
        rows = cursor.fetchall()
        assert len(rows) > 0
        # 3200 / 10000 = 0.32
        assert any(abs(r[0] - 0.32) < 0.01 for r in rows)

    def test_fk_integrity(self, db, silver_parquet):
        """AC #3: FACT rows reference valid DIM keys."""
        loader = FactLoader(db)
        loader.load_from_silver(silver_parquet)

        cursor = db.cursor()
        # All FK references should be valid
        cursor.execute("""
            SELECT COUNT(*) FROM FACT_ENERGY_FLOW f
            WHERE f.id_region NOT IN (SELECT id_region FROM DIM_REGION)
               OR f.id_source NOT IN (SELECT id_source FROM DIM_SOURCE)
               OR f.id_date NOT IN (SELECT id_date FROM DIM_TIME)
        """)
        assert cursor.fetchone()[0] == 0

    def test_idempotent_load(self, db, silver_parquet):
        """Reload same data doesn't create duplicates (ON CONFLICT)."""
        loader = FactLoader(db)
        loader.load_from_silver(silver_parquet)
        count1 = loader.get_fact_count()
        loader.load_from_silver(silver_parquet)
        count2 = loader.get_fact_count()
        assert count1 == count2

    def test_fact_summary(self, db, silver_parquet):
        """Summary stats work correctly."""
        loader = FactLoader(db)
        loader.load_from_silver(silver_parquet)
        summary = loader.get_fact_summary()
        assert summary["total_rows"] > 0
        assert summary["regions"] == 2
