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
    # No CORS needed — the Function App has no HTTP routes (pipeline/timers only).
    # The dataviz API + frontend live separately on the VPS (api/, frontend/).
  }

  app_settings = {
    "KEY_VAULT_URL"              = azurerm_key_vault.main.vault_uri
    "STORAGE_ACCOUNT_NAME"       = azurerm_storage_account.datalake.name
    "SUPABASE_CONNECTION_STRING" = var.supabase_connection_string
    "ENTSOE_API_TOKEN"           = var.entsoe_api_token
    "AzureWebJobsFeatureFlags"   = "EnableWorkerIndexing"  # required for Python v2 decorator model
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

# Frontend + API are no longer hosted on Azure — they run on the VPS
# (docker-compose.yml, api/, frontend/) behind Caddy. Gold data lives in
# Supabase (SUPABASE_CONNECTION_STRING), not Azure SQL.
