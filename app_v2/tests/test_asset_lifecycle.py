"""Tests for asset_discovery.py and asset_lifecycle.py — Story 1.3, Task 5"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from functions.shared.asset_discovery import AssetDiscovery
from functions.shared.asset_lifecycle import AssetLifecycle


@pytest.fixture
def db():
    """In-memory SQLite with DIM_REGION schema (matching migration 001)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE DIM_REGION (
            region_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_insee_region VARCHAR(3) NOT NULL UNIQUE,
            libelle_region VARCHAR(50) NOT NULL,
            status VARCHAR(10) NOT NULL DEFAULT 'active',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


@pytest.fixture
def seeded_db(db):
    """DB with 3 pre-existing regions."""
    now = datetime.now(timezone.utc).isoformat()
    db.executemany(
        """INSERT INTO DIM_REGION
           (code_insee_region, libelle_region, status, first_seen_at, last_seen_at)
           VALUES (?, ?, 'active', ?, ?)""",
        [
            ("11", "Île-de-France", now, now),
            ("24", "Centre-Val de Loire", now, now),
            ("84", "Auvergne-Rhône-Alpes", now, now),
        ],
    )
    db.commit()
    return db


@pytest.fixture
def discovery(db):
    return AssetDiscovery(db_connection=db)


@pytest.fixture
def discovery_seeded(seeded_db):
    return AssetDiscovery(db_connection=seeded_db)


# ─── Asset Discovery Tests ──────────────────────────────────────────────────

class TestAssetDiscovery:
    """AC #1: New regions are discovered and inserted."""

    def test_discover_new_regions(self, discovery, db):
        """New regions found in Bronze are inserted as active."""
        records = [
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
            {"code_insee_region": "24", "libelle_region": "Centre-Val de Loire"},
        ]
        result = discovery.discover_regions(records)
        assert result["new_count"] == 2
        assert result["updated_count"] == 0

        # Verify in DB
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM DIM_REGION WHERE status = 'active'")
        assert cursor.fetchone()[0] == 2

    def test_discover_existing_updates_last_seen(self, discovery_seeded, seeded_db):
        """Existing regions get last_seen_at updated."""
        records = [
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
        ]
        result = discovery_seeded.discover_regions(records)
        assert result["new_count"] == 0
        assert result["updated_count"] == 1

    def test_discover_mixed_new_and_existing(self, discovery_seeded, seeded_db):
        """Mix of new and existing regions."""
        records = [
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
            {"code_insee_region": "93", "libelle_region": "PACA"},
        ]
        result = discovery_seeded.discover_regions(records)
        assert result["new_count"] == 1
        assert result["updated_count"] == 1

    def test_deduplicate_records(self, discovery, db):
        """Duplicate region codes in records are handled."""
        records = [
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
            {"code_insee_region": "11", "libelle_region": "Île-de-France"},
        ]
        result = discovery.discover_regions(records)
        assert result["new_count"] == 1
        assert len(result["regions_seen"]) == 1

    def test_empty_records(self, discovery):
        """Empty records list returns zeroes."""
        result = discovery.discover_regions([])
        assert result["new_count"] == 0
        assert result["updated_count"] == 0

    def test_reactivate_stale_region(self, seeded_db):
        """AC #1: Stale region seen again → reactivated to active."""
        # Make region stale
        seeded_db.execute(
            "UPDATE DIM_REGION SET status = 'stale' WHERE code_insee_region = '11'"
        )
        seeded_db.commit()

        discovery = AssetDiscovery(db_connection=seeded_db)
        records = [{"code_insee_region": "11", "libelle_region": "Île-de-France"}]
        discovery.discover_regions(records)

        cursor = seeded_db.cursor()
        cursor.execute(
            "SELECT status FROM DIM_REGION WHERE code_insee_region = '11'"
        )
        assert cursor.fetchone()[0] == "active"


# ─── Asset Lifecycle Tests ──────────────────────────────────────────────────

class TestAssetLifecycle:
    """AC #2, #3: Stale and inactive detection with soft delete."""

    def test_all_active(self, seeded_db):
        """No stale regions when all recently seen."""
        lifecycle = AssetLifecycle(db_connection=seeded_db)
        result = lifecycle.check_staleness()
        assert result["stale_count"] == 0
        assert result["inactive_count"] == 0

    def test_detect_stale(self, seeded_db):
        """Regions not seen for > staleness threshold become stale."""
        # Set last_seen_at to 48 hours ago
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        seeded_db.execute(
            "UPDATE DIM_REGION SET last_seen_at = ? WHERE code_insee_region = '11'",
            (old_time,),
        )
        seeded_db.commit()

        lifecycle = AssetLifecycle(db_connection=seeded_db)
        result = lifecycle.check_staleness()
        assert result["stale_count"] == 1
        assert "11" in result["stale_regions"]

    def test_detect_inactive(self, seeded_db):
        """Regions not seen for > inactive threshold become inactive."""
        # Set last_seen_at to 10 days ago
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        seeded_db.execute(
            "UPDATE DIM_REGION SET last_seen_at = ? WHERE code_insee_region = '24'",
            (old_time,),
        )
        seeded_db.commit()

        lifecycle = AssetLifecycle(db_connection=seeded_db)
        result = lifecycle.check_staleness()
        assert result["inactive_count"] == 1
        assert "24" in result["inactive_regions"]

    def test_no_hard_delete(self, seeded_db):
        """AC #3: Inactive regions are not deleted, just status updated."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        seeded_db.execute(
            "UPDATE DIM_REGION SET last_seen_at = ?", (old_time,)
        )
        seeded_db.commit()

        lifecycle = AssetLifecycle(db_connection=seeded_db)
        lifecycle.check_staleness()

        cursor = seeded_db.cursor()
        cursor.execute("SELECT COUNT(*) FROM DIM_REGION")
        assert cursor.fetchone()[0] == 3  # All 3 still exist

    def test_status_summary(self, seeded_db):
        """Get count of regions by status."""
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        seeded_db.execute(
            "UPDATE DIM_REGION SET last_seen_at = ? WHERE code_insee_region = '11'",
            (old,),
        )
        seeded_db.commit()

        lifecycle = AssetLifecycle(db_connection=seeded_db)
        lifecycle.check_staleness()

        summary = lifecycle.get_status_summary()
        assert summary.get("active", 0) == 2
        assert summary.get("stale", 0) == 1

    def test_configurable_threshold(self, seeded_db, monkeypatch):
        """Staleness threshold is configurable via env var."""
        monkeypatch.setenv("STALENESS_THRESHOLD_HOURS", "1")

        # Set last_seen_at to 2 hours ago
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        seeded_db.execute(
            "UPDATE DIM_REGION SET last_seen_at = ? WHERE code_insee_region = '84'",
            (old_time,),
        )
        seeded_db.commit()

        lifecycle = AssetLifecycle(db_connection=seeded_db)
        result = lifecycle.check_staleness()
        assert result["stale_count"] == 1
        assert "84" in result["stale_regions"]
