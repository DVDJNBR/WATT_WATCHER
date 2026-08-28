# WATT_WATCHER

Data engineering portfolio piece: an automated ETL pipeline for regional energy analysis using French/European Open Data (RTE, Météo-France, ODRE, ENTSO-E), landing into a medallion (Bronze/Silver/Gold) architecture and surfaced through a public dataviz dashboard.

**Stack:** Azure Functions (Python 3.11, pipeline only) · ADLS Gen2 (Bronze/Silver) · Supabase/PostgreSQL (Gold) · FastAPI (dataviz API) · React/Vite (frontend) · Docker + Caddy on a VPS · Terraform IaC

---

## Architecture

```
RTE API ─┐
Météo-France ├─→ Bronze (ADLS) ─→ Silver (Parquet) ─→ Gold (Supabase) ─→ FastAPI ─→ Dashboard
ODRE / Maintenance ┘         [Azure Functions, cron]                    [VPS, Docker]
```

- **`functions/`** — Azure Functions, pipeline only (no HTTP API). Timer triggers ingest RTE/Météo-France/ODRE/maintenance data on a schedule and load it into Supabase. No auth, no alerting — this is a public showroom, not a monitored product.
- **`api/`** — FastAPI, public read-only dataviz API. Reads Gold data from Supabase. Deployed on the VPS.
- **`frontend/`** — React/Vite dashboard. Deployed on the VPS (static build served by nginx).
- **`.cloud/`** — Terraform for the Azure Functions pipeline (Resource Group, ADLS Gen2, Function App, Key Vault, monitoring). No Azure SQL, no Azure Storage Static Website — those are replaced by Supabase and the VPS.

---

## Local development

### Pipeline / tests (Python)

```bash
uv sync --all-extras
uv run python -m pytest tests/ -q
```

Tests run against SQLite (no Supabase connection needed). Set `LOCAL_GOLD_DB` to point to a local `gold.db`.

### Dataviz API (FastAPI)

```bash
export SUPABASE_CONNECTION_STRING="postgresql://..."   # or DB_TYPE=sqlite + SQLITE_PATH=./gold.db
uv run uvicorn api.main:app --reload --port 8000
```

Swagger UI at `http://localhost:8000/docs` (FastAPI auto-generated).

### Frontend

```bash
cd frontend
npm install
npm run dev   # proxies /api → http://localhost:8000 (see vite.config.js)
```

---

## VPS deployment (Docker + Caddy)

```bash
git clone <repo> /opt/watt-watcher && cd /opt/watt-watcher
cp .env.example .env   # fill in SUPABASE_CONNECTION_STRING
docker compose up -d --build
```

This starts two containers:
- `api` — FastAPI on `127.0.0.1:8002` (internal)
- `frontend` — nginx static build on `127.0.0.1:8001` (internal)

Point Caddy at these ports for `watt-watcher.dvdjnbr.fr` — `handle_path /api/*` → `localhost:8002`, everything else → `localhost:8001`. Caddyfile and DNS are managed outside this repo.

CI (`.github/workflows/deploy.yml`, job `deploy-vps`) redeploys automatically on push to `main` via SSH: `git pull && docker compose up -d --build`. Requires GitHub secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_PROJECT_PATH`.

---

## Azure Functions (pipeline) deployment

```bash
cd .cloud
cp terraform.tfvars.example terraform.tfvars
# Fill in supabase_connection_string in terraform.tfvars

terraform init
terraform apply -auto-approve
./sync_github_secrets.sh   # reads terraform outputs → sets AZURE_FUNCTIONAPP_NAME / AZURE_FUNCTIONAPP_PUBLISH_PROFILE
```

Also requires the `AZURE_CREDENTIALS` GitHub secret (service principal) for the `deploy-functions` CI job.

Push to `main` → GitHub Actions runs tests → deploys the Functions pipeline.

**Timer triggers — one per real refresh cadence, not one job doing everything every 15 minutes regardless of need:**
- `*/15 * * * *` (`pipeline_15min`) — RTE eCO2mix + Open-Meteo, the two sources that genuinely change continuously. Bronze → Silver → Gold.
- `0 6 * * *` (`pipeline_daily`) — ENTSO-E day-ahead prices + ENTSO-E generation-unit outages (A77), both published once a day.
- `0 3 * * 0` (`pipeline_weekly`) — ODRE installed-capacity registry, which the source itself only updates ~once a year.
- `0 1 * * *` — SQL reference snapshot (`DIM_REGION`/`DIM_SOURCE`) → Bronze.

Each stage's fetch/clean/load logic lives in its own module under `functions/shared/stages/`; `function_app.py` only wires timers to stages.

Bronze/Silver blobs are auto-purged by ADLS lifecycle policies (`retention_bronze_days`/`retention_silver_days` in Terraform, default 180/90 days) — no purge job needed in code. Gold tables are never purged.

**Day-ahead prices + generation outages (ENTSO-E):** optional — set `ENTSOE_API_TOKEN` (see `.cloud/terraform.tfvars.example`) to enable both. Ingestion is non-fatal and silently skipped if unset. `fact_maintenance` is fed from ENTSO-E outages (A77) now, not RTE web scraping — the scraper's target URL was never actually wired into Terraform, so it never ran in production; ENTSO-E reuses the same credentials/infra already in place for prices. See `docs/entsoe_price_integration_report.md` for the price-side write-up (schema, how the 40% surplus threshold on the dashboard was calibrated against real prices).

### Manual data population (bootstrap / backfill)

`scripts/` holds one-off, hand-run Python scripts — deliberately not Azure
Functions. They exist for two cases the timers above don't cover: seeding a
brand-new environment with history that predates the automation, and
one-time reference data that has no business running on a schedule. Both
still write through the same Bronze → Silver → Gold path as the timers —
`scripts/backfill_market_prices.py` calls `shared/stages/price_stage.py`'s
own `run()` directly, just with a wider date range, so a manual run can
never diverge from what the automation would have produced. This is what
makes the whole thing reproducible from scratch: point a fresh repo at a
fresh Supabase database, and these scripts (not ad-hoc DB surgery) are what
rebuild the history.

Bootstrap sequence for a brand-new environment:
1. `terraform apply` (above) — Function App + ADLS Gen2, pointed at a fresh Supabase DB.
2. Let `pipeline_15min`/`pipeline_weekly` run naturally for a bit (RTE, météo, capacity — no useful history to backfill, they only ever cared about "now").
3. `uv run python scripts/backfill_market_prices.py` — one-time ENTSO-E day-ahead price backfill, from `fact_energy_flow`'s earliest timestamp up to now, so `fact_market_price` has history overlapping the RTE data from day one instead of trickling in one day at a time from `pipeline_daily`'s 26h lookback.
4. `uv run python scripts/geocode_production_units.py` — one-time (well, occasional) geocoding of ENTSO-E's named production units, for reference data not tied to any fact table.

From that point on, `pipeline_daily`/`pipeline_15min`/`pipeline_weekly` keep everything current; the manual scripts only need re-running if a genuinely new gap opens up (a fresh Supabase DB, a long outage, a new data source).

### Destroy & recreate

```bash
cd .cloud
terraform destroy -auto-approve
terraform apply -auto-approve
./sync_github_secrets.sh
git push origin main
```
