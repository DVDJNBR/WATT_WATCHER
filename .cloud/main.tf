# -----------------------------------------------------------------------------
# GRID_POWER_STREAM — Main Infrastructure
# Story 1.0: IaC with Terraform
# -----------------------------------------------------------------------------

locals {
  tags = {
    project    = "WATT_WATCHER"
    managed_by = "terraform"
  }
}

data "azurerm_client_config" "current" {}

# ─── Resource Group ──────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = "watt-watcher-rg"
  location = var.location
  tags     = local.tags
}

# ─── ADLS Gen2 Storage Account ──────────────────────────────────────────────
resource "azurerm_storage_account" "datalake" {
  name                     = "watchwatcherdatalake"  # no hyphens allowed, 24 char max
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # Hierarchical Namespace = ADLS Gen2

  tags = local.tags
}

# ADLS containers
resource "azurerm_storage_container" "bronze" {
  name                  = "bronze"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "silver" {
  name                  = "silver"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "gold" {
  name                  = "gold"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "audit" {
  name                  = "audit"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

# ─── ADLS Lifecycle Policies (Data Retention) ───────────────────────────────
resource "azurerm_storage_management_policy" "retention" {
  storage_account_id = azurerm_storage_account.datalake.id

  rule {
    name    = "bronze-retention"
    enabled = true
    filters {
      prefix_match = ["bronze/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.retention_bronze_days
      }
    }
  }

  rule {
    name    = "silver-retention"
    enabled = true
    filters {
      prefix_match = ["silver/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.retention_silver_days
      }
    }
  }

  rule {
    name    = "audit-retention"
    enabled = true
    filters {
      prefix_match = ["audit/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.retention_audit_days
      }
    }
  }
}

# ─── Azure SQL Serverless ───────────────────────────────────────────────────
resource "azurerm_mssql_server" "main" {
  name                         = "sql-server-watt-watcher"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_login
  administrator_login_password = var.sql_admin_password

  tags = local.tags
}

resource "azurerm_mssql_database" "warehouse" {
  name      = "database-watt-watcher"
  server_id = azurerm_mssql_server.main.id
  sku_name  = "GP_S_Gen5_1"  # Serverless Gen5, 1 vCore

  auto_pause_delay_in_minutes = var.sql_auto_pause_delay
  min_capacity                = 0.5
  max_size_gb                 = 32

  tags = local.tags
}

# SQL firewall — allow Azure services
resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ─── Azure Key Vault ────────────────────────────────────────────────────────
resource "azurerm_key_vault" "main" {
  name                       = "watt-watcher-key-vault"  # 22 chars — fits 24 char limit
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # Allow deploying user to manage secrets
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "Set", "List", "Delete", "Purge"]
  }

  tags = local.tags
}

# ─── Azure Function App (Consumption Plan) ──────────────────────────────────
resource "azurerm_service_plan" "functions" {
  name                = "service-plan-watt-watcher"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"  # Consumption plan

  tags = local.tags
}

resource "azurerm_storage_account" "functions" {
  name                     = "watchwatcherfunctions"  # no hyphens allowed, 24 char max
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = local.tags
}

resource "azurerm_linux_function_app" "main" {
  name                       = "function-app-watt-watcher"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
    cors {
      allowed_origins = [
        "https://${azurerm_storage_account.frontend.name}.z28.web.core.windows.net",
        "http://localhost:5173",
        "http://localhost:4173",
      ]
    }
  }

  app_settings = {
    "KEY_VAULT_URL"            = azurerm_key_vault.main.vault_uri
    "STORAGE_ACCOUNT_NAME"     = azurerm_storage_account.datalake.name
    "SQL_SERVER"               = azurerm_mssql_server.main.fully_qualified_domain_name
    "SQL_DATABASE"             = azurerm_mssql_database.warehouse.name
    "SQL_CONNECTION_STRING"    = "Driver={ODBC Driver 18 for SQL Server};Server=${azurerm_mssql_server.main.fully_qualified_domain_name};Database=${azurerm_mssql_database.warehouse.name};Uid=${var.sql_admin_login};Pwd=${var.sql_admin_password};Encrypt=yes;TrustServerCertificate=no;"
    "AzureWebJobsFeatureFlags" = "EnableWorkerIndexing"  # required for Python v2 decorator model
  }

  tags = local.tags
}

# ─── RBAC Assignments ───────────────────────────────────────────────────────

# Function → ADLS Gen2: Storage Blob Data Contributor
resource "azurerm_role_assignment" "func_storage" {
  scope                = azurerm_storage_account.datalake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}

# Function → Key Vault: Secrets User
resource "azurerm_key_vault_access_policy" "func_kv" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_function_app.main.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}

# ─── Log Analytics Workspace (required by App Insights v2) ──────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-analytics-watt-watcher"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = local.tags
}

# ─── Application Insights ───────────────────────────────────────────────────
resource "azurerm_application_insights" "main" {
  name                = "app-insights-watt-watcher"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  application_type    = "other"
  workspace_id        = azurerm_log_analytics_workspace.main.id

  tags = local.tags
}

# ─── Frontend Static Website (Azure Storage) ────────────────────────────────
# Azure Static Web Apps is blocked on Student subscriptions (all regions 403)
# → Storage Account with static website hosting = free, no region restriction
resource "azurerm_storage_account" "frontend" {
  name                     = "watchwatcherfrontend"  # no hyphens allowed, 24 char max
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  static_website {
    index_document     = "index.html"
    error_404_document = "index.html"  # SPA fallback for React Router
  }

  tags = local.tags
}

# ─── SQL Schema Initialization ──────────────────────────────────────────────
# Schema is initialized at runtime by ensure_schema() in dim_loader.py
# Manual init: az sql db connect or Azure Cloud Shell with init_schema.sql
resource "null_resource" "sql_seed" {
  triggers = {
    seed_hash = filesha256("${path.module}/sql/seed_dimensions.sql")
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "SQL seed skipped — run manually via Azure Cloud Shell or sqlcmd"
      echo "File: ${path.module}/sql/seed_dimensions.sql"
    EOT
  }

  depends_on = [azurerm_mssql_database.warehouse]
}
