"""
Dimension Table Loader — Story 3.2, Task 1

Upserts DIM_REGION, DIM_TIME, DIM_SOURCE into the Gold Star Schema.
Uses MERGE pattern (INSERT OR REPLACE for SQLite, MERGE for SQL Server).
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DimLoader:
    """Load and upsert dimension tables in the Gold Star Schema."""

    def __init__(self, db_connection: Any):
        self.conn = db_connection
        self._is_sqlite = isinstance(db_connection, sqlite3.Connection)

    def ensure_schema(self) -> None:
        """Create Gold Star Schema tables if they don't exist.

        Works for both SQLite (local dev) and SQL Server (production).
        """
        cursor = self.conn.cursor()

        if self._is_sqlite:
            # executescript() is SQLite-specific
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS DIM_REGION (
                    id_region INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_insee VARCHAR(3) NOT NULL UNIQUE,
                    nom_region VARCHAR(100) NOT NULL,
                    population INTEGER,
                    superficie_km2 REAL
                );

                CREATE TABLE IF NOT EXISTS DIM_TIME (
                    id_date INTEGER PRIMARY KEY AUTOINCREMENT,
                    horodatage TEXT NOT NULL UNIQUE,
                    jour INTEGER NOT NULL,
                    mois INTEGER NOT NULL,
                    annee INTEGER NOT NULL,
                    heure INTEGER NOT NULL,
                    jour_semaine INTEGER,
                    est_weekend INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS DIM_SOURCE (
                    id_source INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name VARCHAR(50) NOT NULL UNIQUE,
                    is_green INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS FACT_ENERGY_FLOW (
                    id_fact INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_date INTEGER NOT NULL REFERENCES DIM_TIME(id_date),
                    id_region INTEGER NOT NULL REFERENCES DIM_REGION(id_region),
                    id_source INTEGER NOT NULL REFERENCES DIM_SOURCE(id_source),
                    valeur_mw REAL NOT NULL,
                    facteur_charge REAL,
                    temperature_moyenne REAL,
                    prix_mwh REAL,
                    consommation_mw REAL NULL,
                    UNIQUE(id_date, id_region, id_source)
                );
            """)
            self.conn.commit()
            logger.info("Gold schema ensured (SQLite)")
        else:
            # PostgreSQL (Supabase): use CREATE TABLE IF NOT EXISTS
            statements = [
                """CREATE TABLE IF NOT EXISTS dim_region (
                       id_region       SERIAL          PRIMARY KEY,
                       code_insee      VARCHAR(5)      NOT NULL UNIQUE,
                       nom_region      VARCHAR(100)    NOT NULL,
                       population      INT             NULL,
                       superficie_km2  INT             NULL,
                       status          VARCHAR(10)     NOT NULL DEFAULT 'active',
                       first_seen_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                       last_seen_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
                   )""",
                """CREATE TABLE IF NOT EXISTS dim_time (
                       id_date         SERIAL          PRIMARY KEY,
                       horodatage      TIMESTAMPTZ     NOT NULL UNIQUE,
                       jour            INT             NOT NULL,
                       mois            INT             NOT NULL,
                       annee           INT             NOT NULL,
                       heure           INT             NOT NULL,
                       minute          INT             NOT NULL DEFAULT 0,
                       jour_semaine    INT             NULL,
                       est_weekend     BOOLEAN         NULL
                   )""",
                """CREATE TABLE IF NOT EXISTS dim_source (
                       id_source       SERIAL          PRIMARY KEY,
                       source_name     VARCHAR(50)     NOT NULL UNIQUE,
                       is_green        BOOLEAN         NOT NULL DEFAULT FALSE,
                       category        VARCHAR(30)     NULL
                   )""",
                """CREATE TABLE IF NOT EXISTS fact_energy_flow (
                       id_fact             BIGSERIAL       PRIMARY KEY,
                       id_date             INT             NOT NULL REFERENCES dim_time(id_date),
                       id_region           INT             NOT NULL REFERENCES dim_region(id_region),
                       id_source           INT             NOT NULL REFERENCES dim_source(id_source),
                       valeur_mw           NUMERIC(10,2)   NULL,
                       taux_couverture     NUMERIC(6,2)    NULL,
                       taux_charge         NUMERIC(6,2)    NULL,
                       facteur_charge      NUMERIC(5,4)    NULL,
                       temperature_moyenne NUMERIC(5,2)    NULL,
                       prix_mwh            NUMERIC(8,2)    NULL,
                       consommation_mw     NUMERIC(10,2)   NULL,
                       ech_physiques_mw    NUMERIC(10,2)   NULL,
                       UNIQUE (id_date, id_region, id_source)
                   )""",
                "CREATE INDEX IF NOT EXISTS ix_fact_region_date ON fact_energy_flow (id_region, id_date)",
                "CREATE INDEX IF NOT EXISTS ix_dim_time_horodatage ON dim_time (horodatage)",
                "CREATE INDEX IF NOT EXISTS ix_dim_region_insee ON dim_region (code_insee)",
            ]
            for stmt in statements:
                cursor.execute(stmt)
            self.conn.commit()
            logger.info("Gold schema ensured (PostgreSQL)")

    def upsert_regions(self, regions: list[dict]) -> int:
        """
        Upsert DIM_REGION from Silver/asset registry data.

        Args:
            regions: List of dicts with code_insee, nom_region, population, superficie_km2.

        Returns:
            Number of rows upserted.
        """
        if not regions:
            return 0
        cursor = self.conn.cursor()
        rows = [
            (r["code_insee"], r["nom_region"], r.get("population"), r.get("superficie_km2"))
            for r in regions
        ]
        if self._is_sqlite:
            cursor.executemany(
                """INSERT INTO DIM_REGION (code_insee, nom_region, population, superficie_km2)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(code_insee) DO UPDATE SET
                       nom_region = excluded.nom_region,
                       population = excluded.population,
                       superficie_km2 = excluded.superficie_km2""",
                rows,
            )
        else:
            # PostgreSQL: batch INSERT ... ON CONFLICT DO UPDATE
            cursor.executemany(
                """INSERT INTO dim_region (code_insee, nom_region, population, superficie_km2)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (code_insee) DO UPDATE SET
                       nom_region = EXCLUDED.nom_region,
                       population = EXCLUDED.population,
                       superficie_km2 = EXCLUDED.superficie_km2""",
                rows,
            )
        self.conn.commit()
        logger.info("Upserted %d regions", len(rows))
        return len(rows)

    def upsert_time(self, timestamps: list[str]) -> int:
        """
        Upsert DIM_TIME entries from timestamp strings.

        Batched to avoid N+1 queries: one MERGE for all timestamps.

        Args:
            timestamps: ISO 8601 datetime strings.
        """
        rows = []
        for ts_str in timestamps:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                logger.debug("Skipping unparseable timestamp: %r", ts_str)
                continue
            rows.append((
                ts_str, ts.day, ts.month, ts.year, ts.hour,
                ts.isoweekday(), 1 if ts.isoweekday() >= 6 else 0,
            ))

        if not rows:
            return 0

        cursor = self.conn.cursor()
        if self._is_sqlite:
            cursor.executemany(
                """INSERT INTO DIM_TIME
                   (horodatage, jour, mois, annee, heure, jour_semaine, est_weekend)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(horodatage) DO NOTHING""",
                rows,
            )
        else:
            # PostgreSQL: batch INSERT ... ON CONFLICT DO NOTHING
            cursor.executemany(
                """INSERT INTO dim_time
                   (horodatage, jour, mois, annee, heure, jour_semaine, est_weekend)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (horodatage) DO NOTHING""",
                rows,
            )
        self.conn.commit()
        logger.info("Upserted %d time entries", len(rows))
        return len(rows)

    def upsert_sources(self, sources: list[dict] | None = None) -> int:
        """
        Upsert DIM_SOURCE with energy source types.

        Uses default French source list if none provided.
        """
        if sources is None:
            sources = [
                {"source_name": "nucleaire", "is_green": False},
                {"source_name": "eolien", "is_green": True},
                {"source_name": "solaire", "is_green": True},
                {"source_name": "hydraulique", "is_green": True},
                {"source_name": "gaz", "is_green": False},
                {"source_name": "charbon", "is_green": False},
                {"source_name": "fioul", "is_green": False},
                {"source_name": "bioenergies", "is_green": True},
            ]

        cursor = self.conn.cursor()
        count = 0
        for s in sources:
            if self._is_sqlite:
                cursor.execute(
                    """INSERT INTO DIM_SOURCE (source_name, is_green)
                       VALUES (?, ?)
                       ON CONFLICT(source_name) DO UPDATE SET
                           is_green = excluded.is_green""",
                    (s["source_name"], s["is_green"]),
                )
            else:
                cursor.execute(
                    """INSERT INTO dim_source (source_name, is_green)
                       VALUES (%s, %s)
                       ON CONFLICT (source_name) DO UPDATE SET
                           is_green = EXCLUDED.is_green""",
                    (s["source_name"], s["is_green"]),
                )
            count += 1
        self.conn.commit()
        logger.info("Upserted %d sources", count)
        return count

    def get_region_id(self, code_insee: str) -> int | None:
        """Get id_region for a given code_insee."""
        cursor = self.conn.cursor()
        ph = "?" if self._is_sqlite else "%s"
        tbl = "DIM_REGION" if self._is_sqlite else "dim_region"
        cursor.execute(f"SELECT id_region FROM {tbl} WHERE code_insee = {ph}", (code_insee,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_time_id(self, horodatage: str) -> int | None:
        """Get id_date for a given horodatage."""
        cursor = self.conn.cursor()
        ph = "?" if self._is_sqlite else "%s"
        tbl = "DIM_TIME" if self._is_sqlite else "dim_time"
        cursor.execute(f"SELECT id_date FROM {tbl} WHERE horodatage = {ph}", (horodatage,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_source_id(self, source_name: str) -> int | None:
        """Get id_source for a given source name."""
        cursor = self.conn.cursor()
        ph = "?" if self._is_sqlite else "%s"
        tbl = "DIM_SOURCE" if self._is_sqlite else "dim_source"
        cursor.execute(f"SELECT id_source FROM {tbl} WHERE source_name = {ph}", (source_name,))
        row = cursor.fetchone()
        return row[0] if row else None
