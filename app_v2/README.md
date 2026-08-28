# WATT_WATCHER

Data engineering portfolio piece: an automated ETL pipeline for regional energy analysis using French Open Data (RTE, Météo-France, ODRE, grid maintenance), landing into a medallion (Bronze/Silver/Gold) architecture and surfaced through a public dataviz dashboard.

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

**Timer triggers:**
- `*/15 * * * *` — full pipeline (Bronze → Silver → Gold) for all sources: RTE eCO2mix, Open-Meteo, ODRE capacity, grid maintenance, and ENTSO-E day-ahead prices. Every source writes raw Bronze and cleaned Silver Parquet before loading Gold.
- `0 1 * * *` — SQL reference snapshot (`DIM_REGION`/`DIM_SOURCE`) → Bronze

Bronze/Silver blobs are auto-purged by ADLS lifecycle policies (`retention_bronze_days`/`retention_silver_days` in Terraform, default 180/90 days) — no purge job needed in code. Gold tables are never purged.

**Day-ahead market prices (ENTSO-E):** optional — set `ENTSOE_API_TOKEN` (see `.cloud/terraform.tfvars.example`) to enable. Ingestion is non-fatal and silently skipped if unset. See `docs/entsoe_price_integration_report.md` for the full write-up (schema, how the 40% surplus threshold on the dashboard was calibrated against real prices).

### Destroy & recreate

```bash
cd .cloud
terraform destroy -auto-approve
terraform apply -auto-approve
./sync_github_secrets.sh
git push origin main
```
