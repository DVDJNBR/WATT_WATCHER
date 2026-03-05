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
                    UNIQUE(id_date, id_region, id_source)
                );
            """)
            self.conn.commit()
            logger.info("Gold schema ensured (SQLite)")
        else:
            # SQL Server: use IF NOT EXISTS pattern with INFORMATION_SCHEMA
            statements = [
                """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='DIM_REGION')
                   CREATE TABLE DIM_REGION (
                       id_region       INT             PRIMARY KEY IDENTITY(1,1),
                       code_insee      VARCHAR(5)      NOT NULL UNIQUE,
                       nom_region      NVARCHAR(100)   NOT NULL,
                       population      INT             NULL,
                       superficie_km2  INT             NULL,
                       status          VARCHAR(10)     NOT NULL DEFAULT 'active',
                       first_seen_at   DATETIME2       NOT NULL DEFAULT GETDATE(),
                       last_seen_at    DATETIME2       NOT NULL DEFAULT GETDATE()
                   )""",
                """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='DIM_TIME')
                   CREATE TABLE DIM_TIME (
                       id_date         INT             PRIMARY KEY IDENTITY(1,1),
                       horodatage      DATETIME2       NOT NULL UNIQUE,
                       jour            INT             NOT NULL,
                       mois            INT             NOT NULL,
                       annee           INT             NOT NULL,
                       heure           INT             NOT NULL,
                       minute          INT             NOT NULL DEFAULT 0,
                       jour_semaine    INT             NULL,
                       est_weekend     BIT             NULL
                   )""",
                """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='DIM_SOURCE')
                   CREATE TABLE DIM_SOURCE (
                       id_source       INT             PRIMARY KEY IDENTITY(1,1),
                       source_name     NVARCHAR(50)    NOT NULL UNIQUE,
                       is_green        BIT             NOT NULL DEFAULT 0,
                       category        NVARCHAR(30)    NULL
                   )""",
                """IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='FACT_ENERGY_FLOW')
                   CREATE TABLE FACT_ENERGY_FLOW (
                       id_fact             BIGINT          PRIMARY KEY IDENTITY(1,1),
                       id_date             INT             NOT NULL REFERENCES DIM_TIME(id_date),
                       id_region           INT             NOT NULL REFERENCES DIM_REGION(id_region),
                       id_source           INT             NOT NULL REFERENCES DIM_SOURCE(id_source),
                       valeur_mw           DECIMAL(10,2)   NULL,
                       taux_couverture     DECIMAL(6,2)    NULL,
                       taux_charge         DECIMAL(6,2)    NULL,
                       facteur_charge      DECIMAL(5,4)    NULL,
                       temperature_moyenne DECIMAL(5,2)    NULL,
                       prix_mwh            DECIMAL(8,2)    NULL,
                       consommation_mw     DECIMAL(10,2)   NULL,
                       ech_physiques_mw    DECIMAL(10,2)   NULL
                   )""",
                """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_FACT_region_date')
                   CREATE INDEX IX_FACT_region_date ON FACT_ENERGY_FLOW (id_region, id_date)""",
                """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_DIM_TIME_horodatage')
                   CREATE INDEX IX_DIM_TIME_horodatage ON DIM_TIME (horodatage)""",
                """IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_DIM_REGION_insee')
                   CREATE INDEX IX_DIM_REGION_insee ON DIM_REGION (code_insee)""",
            ]
            for stmt in statements:
                cursor.execute(stmt)
            self.conn.commit()
            logger.info("Gold schema ensured (SQL Server)")

    def upsert_regions(self, regions: list[dict]) -> int:
        """
        Upsert DIM_REGION from Silver/asset registry data.

        Args:
            regions: List of dicts with code_insee, nom_region, population, superficie_km2.

        Returns:
            Number of rows upserted.
        """
        cursor = self.conn.cursor()
        count = 0
        for r in regions:
            if self._is_sqlite:
                cursor.execute(
                    """INSERT INTO DIM_REGION (code_insee, nom_region, population, superficie_km2)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(code_insee) DO UPDATE SET
                           nom_region = excluded.nom_region,
                           population = excluded.population,
                           superficie_km2 = excluded.superficie_km2""",
                    (r["code_insee"], r["nom_region"],
                     r.get("population"), r.get("superficie_km2")),
                )
            else:
                # T-SQL MERGE for Azure SQL
                cursor.execute(
                    """MERGE DIM_REGION AS t
                       USING (VALUES (?, ?, ?, ?))
                           AS s(code_insee, nom_region, population, superficie_km2)
                       ON t.code_insee = s.code_insee
                       WHEN MATCHED THEN UPDATE SET
                           nom_region = s.nom_region,
                           population = s.population,
                           superficie_km2 = s.superficie_km2
                       WHEN NOT MATCHED THEN INSERT
                           (code_insee, nom_region, population, superficie_km2)
                           VALUES (s.code_insee, s.nom_region, s.population, s.superficie_km2);""",
                    (r["code_insee"], r["nom_region"],
                     r.get("population"), r.get("superficie_km2")),
                )
            count += 1
        self.conn.commit()
        logger.info("Upserted %d regions", count)
        return count

    def upsert_time(self, timestamps: list[str]) -> int:
        """
        Upsert DIM_TIME entries from timestamp strings.

        Args:
            timestamps: ISO 8601 datetime strings.
        """
        cursor = self.conn.cursor()
        count = 0
        for ts_str in timestamps:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            params = (
                ts_str, ts.day, ts.month, ts.year, ts.hour,
                ts.isoweekday(), 1 if ts.isoweekday() >= 6 else 0,
            )
            if self._is_sqlite:
                cursor.execute(
                    """INSERT INTO DIM_TIME
                       (horodatage, jour, mois, annee, heure, jour_semaine, est_weekend)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(horodatage) DO NOTHING""",
                    params,
                )
            else:
                cursor.execute(
                    """MERGE DIM_TIME AS t
                       USING (VALUES (?, ?, ?, ?, ?, ?, ?))
                           AS s(horodatage, jour, mois, annee, heure, jour_semaine, est_weekend)
                       ON t.horodatage = s.horodatage
                       WHEN NOT MATCHED THEN INSERT
                           (horodatage, jour, mois, annee, heure, jour_semaine, est_weekend)
                           VALUES (s.horodatage, s.jour, s.mois, s.annee,
                                   s.heure, s.jour_semaine, s.est_weekend);""",
                    params,
                )
            count += 1
        self.conn.commit()
        logger.info("Upserted %d time entries", count)
        return count

    def upsert_sources(self, sources: list[dict] | None = None) -> int:
        """
        Upsert DIM_SOURCE with energy source types.

        Uses default French source list if none provided.
        """
        if sources is None:
            sources = [
                {"source_name": "nucleaire", "is_green": 0},
                {"source_name": "eolien", "is_green": 1},
                {"source_name": "solaire", "is_green": 1},
                {"source_name": "hydraulique", "is_green": 1},
                {"source_name": "gaz", "is_green": 0},
                {"source_name": "charbon", "is_green": 0},
                {"source_name": "fioul", "is_green": 0},
                {"source_name": "bioenergies", "is_green": 1},
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
                    """MERGE DIM_SOURCE AS t
                       USING (VALUES (?, ?)) AS s(source_name, is_green)
                       ON t.source_name = s.source_name
                       WHEN MATCHED THEN UPDATE SET is_green = s.is_green
                       WHEN NOT MATCHED THEN INSERT (source_name, is_green)
                           VALUES (s.source_name, s.is_green);""",
                    (s["source_name"], s["is_green"]),
                )
            count += 1
        self.conn.commit()
        logger.info("Upserted %d sources", count)
        return count

    def get_region_id(self, code_insee: str) -> int | None:
        """Get id_region for a given code_insee."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id_region FROM DIM_REGION WHERE code_insee = ?", (code_insee,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_time_id(self, horodatage: str) -> int | None:
        """Get id_date for a given horodatage."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id_date FROM DIM_TIME WHERE horodatage = ?", (horodatage,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_source_id(self, source_name: str) -> int | None:
        """Get id_source for a given source name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id_source FROM DIM_SOURCE WHERE source_name = ?", (source_name,))
        row = cursor.fetchone()
        return row[0] if row else None
