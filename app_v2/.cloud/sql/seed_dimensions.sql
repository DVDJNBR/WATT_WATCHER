-- =============================================================================
-- GRID_POWER_STREAM — Dimension Seed Data
-- Generated from Story 0.1 API Exploration (2026-02-25)
-- =============================================================================

-- ─── DIM_SOURCE seed ─────────────────────────────────────────────────────────
-- Energy sources discovered from eco2mix-regional-tr API response fields.
-- category: 'production' (generates power), 'storage' (battery), 'exchange' (cross-border)

INSERT INTO DIM_SOURCE (source_name, is_green, category) VALUES
    ('thermique',           0, 'production'),
    ('nucleaire',           0, 'production'),
    ('eolien',              1, 'production'),
    ('solaire',             1, 'production'),
    ('hydraulique',         1, 'production'),
    ('pompage',             0, 'storage'),
    ('bioenergies',         1, 'production'),
    ('stockage_batterie',   0, 'storage'),
    ('destockage_batterie', 0, 'storage');

-- ─── DIM_REGION seed ─────────────────────────────────────────────────────────
-- 12 metropolitan regions discovered via API region discovery.
-- Population/superficie left NULL for future enrichment (INSEE data).

INSERT INTO DIM_REGION (code_insee, nom_region) VALUES
    ('11', N'Île-de-France'),
    ('24', N'Centre-Val de Loire'),
    ('27', N'Bourgogne-Franche-Comté'),
    ('28', N'Normandie'),
    ('32', N'Hauts-de-France'),
    ('44', N'Grand Est'),
    ('52', N'Pays de la Loire'),
    ('53', N'Bretagne'),
    ('75', N'Nouvelle-Aquitaine'),
    ('76', N'Occitanie'),
    ('84', N'Auvergne-Rhône-Alpes'),
    ('93', N'Provence-Alpes-Côte d''Azur');
