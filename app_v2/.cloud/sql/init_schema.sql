-- =============================================================================
-- WATT_WATCHER — Gold Layer Star Schema (PostgreSQL / Supabase)
-- =============================================================================
--
-- Bootstrap script to reproduce the Gold database from scratch on a fresh
-- Supabase/PostgreSQL project (`psql "$SUPABASE_CONNECTION_STRING" -f init_schema.sql`).
--
-- This is a hand-maintained MIRROR of the real source of truth, which is
-- functions/shared/gold/dim_loader.py::DimLoader.ensure_schema() — the
-- pipeline re-applies that Python code idempotently on every run (CREATE
-- TABLE IF NOT EXISTS), so production never actually depends on this file.
-- It exists purely for reproducibility/documentation: anyone cloning the
-- repo to stand up their own instance, or auditing the schema, can read
-- pure SQL instead of Python control flow. Keep the two in sync by hand
-- when either changes — see docs/data_model.md for the full write-up.
--
-- Dimension tables first, then fact tables (FK order).
-- =============================================================================

-- 1. dim_region
-- Source: RTE eco2mix-regional-tr -> code_insee_region, libelle_region
CREATE TABLE IF NOT EXISTS dim_region (
    id_region       SERIAL          PRIMARY KEY,
    code_insee      VARCHAR(5)      NOT NULL UNIQUE,
    nom_region      VARCHAR(100)    NOT NULL,
    population      INT             NULL,       -- enrichment, not currently populated
    superficie_km2  INT             NULL,       -- enrichment, not currently populated
    status          VARCHAR(10)     NOT NULL DEFAULT 'active',  -- active / stale / inactive
    first_seen_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_dim_region_insee ON dim_region (code_insee);

-- 2. dim_time
-- Source: RTE eco2mix-regional-tr -> date, heure, date_heure
-- Granularity: 15-minute settlement period.
CREATE TABLE IF NOT EXISTS dim_time (
    id_date         SERIAL          PRIMARY KEY,
    horodatage      TIMESTAMPTZ     NOT NULL UNIQUE,
    jour            INT             NOT NULL,   -- 1-31
    mois            INT             NOT NULL,   -- 1-12
    annee           INT             NOT NULL,
    heure           INT             NOT NULL,   -- 0-23
    minute          INT             NOT NULL DEFAULT 0,  -- 0, 15, 30, 45
    jour_semaine    INT             NULL,       -- 1=lundi ... 7=dimanche
    est_weekend     BOOLEAN         NULL
);
CREATE INDEX IF NOT EXISTS ix_dim_time_horodatage ON dim_time (horodatage);

-- 3. dim_source
-- Energy source types (production, storage, exchange).
CREATE TABLE IF NOT EXISTS dim_source (
    id_source       SERIAL          PRIMARY KEY,
    source_name     VARCHAR(50)     NOT NULL UNIQUE,
    is_green        BOOLEAN         NOT NULL DEFAULT FALSE,
    category        VARCHAR(30)     NULL        -- 'production' / 'storage' / 'exchange'
);

-- 4. fact_energy_flow
-- One row per (region, timestamp, source). Core RTE production/consumption fact.
CREATE TABLE IF NOT EXISTS fact_energy_flow (
    id_fact             BIGSERIAL       PRIMARY KEY,
    id_date             INT             NOT NULL REFERENCES dim_time(id_date),
    id_region           INT             NOT NULL REFERENCES dim_region(id_region),
    id_source           INT             NOT NULL REFERENCES dim_source(id_source),
    valeur_mw           NUMERIC(10,2)   NULL,
    taux_couverture     NUMERIC(6,2)    NULL,   -- tco_* from API (% of consumption)
    taux_charge         NUMERIC(6,2)    NULL,   -- tch_* from API (% of installed capacity)
    facteur_charge      NUMERIC(5,4)    NULL,   -- valeur_mw / capacite_installee
    temperature_moyenne NUMERIC(5,2)    NULL,   -- deprecated in favor of fact_meteo
    prix_mwh            NUMERIC(8,2)    NULL,   -- deprecated in favor of fact_market_price
    consommation_mw     NUMERIC(10,2)   NULL,   -- regional consumption for this region/time
    ech_physiques_mw    NUMERIC(10,2)   NULL,   -- physical exchanges (import/export)
    UNIQUE (id_date, id_region, id_source)
);
CREATE INDEX IF NOT EXISTS ix_fact_region_date ON fact_energy_flow (id_region, id_date);

-- 5. fact_meteo
-- Source: Open-Meteo (ERA5 reanalysis), per region centroid.
CREATE TABLE IF NOT EXISTS fact_meteo (
    id_fact             BIGSERIAL       PRIMARY KEY,
    id_date             INT             NOT NULL REFERENCES dim_time(id_date),
    id_region           INT             NOT NULL REFERENCES dim_region(id_region),
    temperature_c       NUMERIC(5,2)    NULL,
    wind_speed_10m      NUMERIC(6,2)    NULL,
    cloudcover_pct      NUMERIC(5,2)    NULL,
    UNIQUE (id_date, id_region)
);
CREATE INDEX IF NOT EXISTS ix_fact_meteo_region_date ON fact_meteo (id_region, id_date);

-- 6. fact_capacity
-- Installed capacity per region/source/year (RTE reference data, low-frequency refresh).
CREATE TABLE IF NOT EXISTS fact_capacity (
    id_fact                 BIGSERIAL       PRIMARY KEY,
    id_region               INT             NOT NULL REFERENCES dim_region(id_region),
    id_source               INT             NOT NULL REFERENCES dim_source(id_source),
    puissance_installee_mw  NUMERIC(10,2)   NULL,
    annee                   INT             NULL,
    UNIQUE (id_region, id_source, annee)
);

-- 7. fact_maintenance
-- Grid maintenance/outage events scraped daily (RTE).
CREATE TABLE IF NOT EXISTS fact_maintenance (
    id_fact         BIGSERIAL       PRIMARY KEY,
    event_id        VARCHAR(100)    NOT NULL UNIQUE,
    id_region       INT             REFERENCES dim_region(id_region),
    unit_name       VARCHAR(200)    NULL,
    event_type      VARCHAR(100)    NULL,
    start_date      TIMESTAMPTZ     NULL,
    end_date        TIMESTAMPTZ     NULL,
    unavailable_mw  NUMERIC(10,2)   NULL,
    scraped_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 8. fact_market_price
-- Source: ENTSO-E Transparency Platform, documentType=A44 (day-ahead prices).
-- One row per market time unit -- France is a single national bidding zone
-- (no per-region split), so this ties to dim_time only, never dim_region.
-- Resolution: hourly (PT60M) before 2025-10-01, 15-minute (PT15M) since
-- (European SDAC market-time-unit transition) -- dim_time already supports
-- 15-min granularity, no schema change needed for that shift.
-- Refreshed every 15 min alongside fact_energy_flow; purged daily beyond
-- PRICE_RETENTION_DAYS (see functions/shared/price_retention.py) -- this
-- table is a short-lived live/calibration cache, not a historical archive
-- (ENTSO-E remains the durable source of truth for that).
CREATE TABLE IF NOT EXISTS fact_market_price (
    id_fact         BIGSERIAL       PRIMARY KEY,
    id_date         INT             NOT NULL UNIQUE REFERENCES dim_time(id_date),
    price_eur_mwh   NUMERIC(10,2)   NOT NULL,
    retrieved_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fact_market_price_date ON fact_market_price (id_date);
