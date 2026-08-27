-- =============================================================================
-- GRID_POWER_STREAM — Gold Layer Star Schema
-- Generated from Story 0.1 API Exploration (2026-02-25)
--
-- Validated against actual RTE eCO2mix Opendatasoft API responses.
-- =============================================================================

-- ─── DIM_REGION ──────────────────────────────────────────────────────────────
-- Source: eco2mix-regional-tr → code_insee_region, libelle_region
-- 12 metropolitan regions discovered via API.
CREATE TABLE DIM_REGION (
    id_region       INT             PRIMARY KEY IDENTITY(1,1),
    code_insee      VARCHAR(5)      NOT NULL UNIQUE,
    nom_region      NVARCHAR(100)   NOT NULL,
    population      INT             NULL,       -- enrichment (INSEE, future)
    superficie_km2  INT             NULL,       -- enrichment (INSEE, future)
    status          VARCHAR(10)     NOT NULL DEFAULT 'active',  -- Story 1.3: active/stale/inactive
    first_seen_at   DATETIME2       NOT NULL DEFAULT GETDATE(),
    last_seen_at    DATETIME2       NOT NULL DEFAULT GETDATE()
);

-- ─── DIM_TIME ────────────────────────────────────────────────────────────────
-- Source: eco2mix-regional-tr → date, heure, date_heure
-- Granularity: 15-minute ISP (Imbalance Settlement Period)
CREATE TABLE DIM_TIME (
    id_date         INT             PRIMARY KEY IDENTITY(1,1),
    horodatage      DATETIME2       NOT NULL UNIQUE,
    jour            INT             NOT NULL,   -- 1-31
    mois            INT             NOT NULL,   -- 1-12
    annee           INT             NOT NULL,
    heure           INT             NOT NULL,   -- 0-23
    minute          INT             NOT NULL DEFAULT 0,  -- 0, 15, 30, 45
    jour_semaine    INT             NULL,       -- 1=lundi, 7=dimanche
    est_weekend     BIT             NULL
);

-- ─── DIM_SOURCE ──────────────────────────────────────────────────────────────
-- Source: eco2mix-regional-tr field names for production columns
-- 9 energy source types discovered in regional API.
CREATE TABLE DIM_SOURCE (
    id_source       INT             PRIMARY KEY IDENTITY(1,1),
    source_name     NVARCHAR(50)    NOT NULL UNIQUE,
    is_green        BIT             NOT NULL DEFAULT 0,
    category        NVARCHAR(30)    NULL        -- 'production', 'storage', 'exchange'
);

-- ─── FACT_ENERGY_FLOW ────────────────────────────────────────────────────────
-- One row per (region, timestamp, source).
-- valeur_mw from API production fields.
-- tco/tch from API tco_*/tch_* fields (already computed by RTE).
CREATE TABLE FACT_ENERGY_FLOW (
    id_fact             BIGINT          PRIMARY KEY IDENTITY(1,1),
    id_date             INT             NOT NULL REFERENCES DIM_TIME(id_date),
    id_region           INT             NOT NULL REFERENCES DIM_REGION(id_region),
    id_source           INT             NOT NULL REFERENCES DIM_SOURCE(id_source),
    valeur_mw           DECIMAL(10,2)   NULL,
    taux_couverture     DECIMAL(6,2)    NULL,   -- tco_* from API (% of consumption)
    taux_charge         DECIMAL(6,2)    NULL,   -- tch_* from API (% of installed capacity)
    facteur_charge      DECIMAL(5,4)    NULL,   -- calculated: valeur_mw / capacite_installee
    temperature_moyenne DECIMAL(5,2)    NULL,   -- from ERA5 (Story 2.2, future)
    prix_mwh            DECIMAL(8,2)    NULL,   -- from EPEX SPOT (future, nullable)
    consommation_mw     DECIMAL(10,2)   NULL,   -- total consumption for this region/time
    ech_physiques_mw    DECIMAL(10,2)   NULL    -- physical exchanges (import/export)
);

-- ─── Indexes for API performance (NFR-P2: <500ms) ───────────────────────────
CREATE INDEX IX_FACT_region_date ON FACT_ENERGY_FLOW (id_region, id_date);
CREATE INDEX IX_FACT_source ON FACT_ENERGY_FLOW (id_source);
CREATE INDEX IX_DIM_TIME_horodatage ON DIM_TIME (horodatage);
CREATE INDEX IX_DIM_REGION_insee ON DIM_REGION (code_insee);

-- ─── FACT_MARKET_PRICE ───────────────────────────────────────────────────────
-- Source: ENTSO-E Transparency Platform, documentType=A44 (day-ahead prices).
-- One row per market time unit — France is a single national bidding zone
-- (no per-region split), so this ties to DIM_TIME only, never DIM_REGION.
-- Resolution: hourly (PT60M) before 2025-10-01, 15-minute (PT15M) since
-- (European SDAC market-time-unit transition) — DIM_TIME already supports
-- 15-min granularity, no schema change needed for that shift.
-- Refreshed every 15 min alongside FACT_ENERGY_FLOW; purged daily beyond
-- PRICE_RETENTION_DAYS (see functions/shared/price_retention.py) — this
-- table is a short-lived live/calibration cache, not a historical archive
-- (ENTSO-E remains the durable source of truth for that).
CREATE TABLE FACT_MARKET_PRICE (
    id_fact         BIGINT          PRIMARY KEY IDENTITY(1,1),
    id_date         INT             NOT NULL UNIQUE REFERENCES DIM_TIME(id_date),
    price_eur_mwh   DECIMAL(10,2)   NOT NULL,
    retrieved_at    DATETIME2       NOT NULL DEFAULT GETDATE()
);

CREATE INDEX IX_FACT_MARKET_PRICE_date ON FACT_MARKET_PRICE (id_date);

-- NOTE (documentation drift, pre-existing — not introduced by this change):
-- this file predates the Supabase/PostgreSQL migration and the
-- fact_meteo / fact_capacity / fact_maintenance tables, all three already
-- live in production (created at runtime by
-- functions/shared/gold/dim_loader.py DimLoader.ensure_schema(), which is
-- the actual schema source of truth) but never backfilled here. Left as-is
-- to keep this change scoped to FACT_MARKET_PRICE; worth a follow-up pass
-- if this file is meant to stay authoritative documentation.
