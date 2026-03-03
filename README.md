# GRID_POWER_STREAM

Automated ETL pipeline for regional energy analysis using French Open Data (RTE, INSEE, Météo-France) to monitor grid load and power distribution.

**Stack:** Azure Functions (Python 3.11) · ADLS Gen2 · Azure SQL Serverless · React/Vite frontend · Terraform IaC

---

## First-time setup

### 1. Prerequisites

```bash
az login
terraform -version   # >= 1.5
gh auth login
```

### 2. Provision infrastructure

```bash
cd .cloud
cp terraform.tfvars.example terraform.tfvars
# Fill in sql_admin_password in terraform.tfvars

terraform init
terraform apply -auto-approve
```

### 3. Push infra outputs to GitHub secrets

```bash
./sync_github_secrets.sh   # reads terraform outputs → sets all GitHub secrets
```

This sets:
- `AZURE_FUNCTIONAPP_NAME`
- `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`
- `AZURE_FUNCTIONS_URL`
- `AZURE_FRONTEND_STORAGE_NAME`
- `AZURE_FRONTEND_STORAGE_KEY`

### 4. Set remaining GitHub secrets manually

In **Settings → Secrets → Actions**:

| Secret | Description |
|---|---|
| `AZURE_CLIENT_ID` | App registration client ID (for frontend auth) |
| `AZURE_TENANT_ID` | Azure AD tenant ID |

### 5. Push to main → deploy

```bash
git push origin main
```

GitHub Actions runs tests → deploys Azure Functions (Oryx build) → deploys frontend.

---

## Destroy & recreate

```bash
cd .cloud
terraform destroy -auto-approve
terraform apply -auto-approve
./sync_github_secrets.sh   # secrets follow the new random name automatically
git push origin main        # redeploy
```

---

## Local development

```bash
uv sync --all-extras
uv run python -m pytest tests/ -q
```

**Tests** run against SQLite (no Azure connection needed). Set `LOCAL_GOLD_DB` to point to a local `gold.db`.

---

## Architecture

```
RTE API ─┐
CSV      ├─→ Bronze (ADLS) ─→ Silver (Parquet) ─→ Gold (Azure SQL) ─→ API ─→ Dashboard
ERA5     ┘                                                              ↑
Maintenance scraping ──────────────────────────────────────────────────┘
```

**Azure Functions triggers:**
- `*/15 * * * *` — RTE ingestion → Bronze → Silver → Gold
- HTTP — `/api/health`, `/api/v1/production/regional`, `/api/v1/export/csv`, `/api/v1/alerts`
