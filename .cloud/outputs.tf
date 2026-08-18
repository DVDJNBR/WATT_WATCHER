# -----------------------------------------------------------------------------
# GRID_POWER_STREAM — Outputs
# -----------------------------------------------------------------------------

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "storage_account_name" {
  description = "ADLS Gen2 Storage Account name"
  value       = azurerm_storage_account.datalake.name
}

output "key_vault_uri" {
  description = "Key Vault URI for secrets retrieval"
  value       = azurerm_key_vault.main.vault_uri
}

output "key_vault_name" {
  description = "Key Vault name (for az keyvault secret show)"
  value       = azurerm_key_vault.main.name
}

output "function_app_name" {
  value = azurerm_linux_function_app.main.name
}

output "function_app_default_hostname" {
  value = azurerm_linux_function_app.main.default_hostname
}

output "application_insights_connection_string" {
  description = "App Insights connection string for Function App"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}


