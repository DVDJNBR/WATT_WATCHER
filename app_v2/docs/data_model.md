# Data model — Gold layer star schema

Reference documentation for the Gold layer (Supabase/PostgreSQL). The
reproducible bootstrap script is [`../.cloud/sql/init_schema.sql`](../.cloud/sql/init_schema.sql);
the schema actually applied in production/tests is
[`functions/shared/gold/dim_loader.py`](../functions/shared/gold/dim_loader.py)
(`DimLoader.ensure_schema()`, idempotent `CREATE TABLE IF NOT EXISTS`, run on
every pipeline execution) — the two are kept in sync by hand, `dim_loader.py`
is the authority if they ever disagree.

## Star schema

```
dim_region ──┐
             ├──< fact_energy_flow >── dim_source
dim_time ────┤
             ├──< fact_meteo
             ├──< fact_market_price
             │
dim_region ──┴──< fact_capacity >── dim_source
dim_region ──────< fact_maintenance
```

| Table | Grain | Source | Refresh |
|---|---|---|---|
| `dim_region` | 1 row / French metropolitan region | RTE eco2mix | on new region seen |
| `dim_time` | 1 row / 15-min settlement period | RTE eco2mix | every 15 min |
| `dim_source` | 1 row / energy source type | static list (8 sources) | rarely |
| `fact_energy_flow` | region × time × source | RTE eco2mix-regional-tr | every 15 min |
| `fact_meteo` | region × time | Open-Meteo (ERA5) | every 15 min |
| `fact_capacity` | region × source × year | ODRE reference registry | weekly (source itself changes ~yearly) |
| `fact_maintenance` | 1 row / outage event | ENTSO-E generation outages (A77) | daily |
| `fact_market_price` | 1 row / time (national, no region split) | ENTSO-E Transparency (A44) | daily, no purge — full history kept like every other fact table |

Every source above genuinely goes through Bronze (raw JSON/CSV, ADLS)
→ Silver (cleaned Parquet, ADLS, Hive-partitioned) → Gold — this table only
covers the Gold layer. Bronze/Silver blobs are auto-purged by ADLS lifecycle
policies (`retention_bronze_days`/`retention_silver_days` in Terraform, not
by application code); Gold rows are never purged for any table.

## Why `fact_market_price` has no `id_region`

France is a single day-ahead bidding zone on ENTSO-E/EPEX — there is no
regional price to attach. Joining it to the rest of the schema is always
`fact_market_price.id_date = dim_time.id_date`, independent of region.
See [`entsoe_price_integration_report.md`](entsoe_price_integration_report.md)
(local, gitignored) for the full design rationale and the threshold
calibration numbers that motivated adding this table.

## Known gaps (not fixed by this pass, flagged for the next documentation round)

- The schema diagram (`frontend/public/diagrams/db-schema-dark.svg`, used on
  the Pipeline page) only shows the original 4-table core
  (`dim_region`/`dim_time`/`dim_source`/`fact_energy_flow`) — `fact_meteo`,
  `fact_capacity`, `fact_maintenance`, and `fact_market_price` were added
  after it was generated. Regenerating it is scoped into the upcoming
  pipeline-page rework, not done here.
- `dim_region.population` / `superficie_km2` are declared but never
  populated (planned enrichment, not yet implemented).
- `fact_energy_flow.temperature_moyenne` / `prix_mwh` predate `fact_meteo`
  and `fact_market_price` respectively and are effectively deprecated
  columns kept for backward compatibility with historical rows — new code
  should read from the dedicated fact tables instead.
