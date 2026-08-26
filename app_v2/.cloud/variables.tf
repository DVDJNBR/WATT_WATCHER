# -----------------------------------------------------------------------------
# GRID_POWER_STREAM — Input Variables
# -----------------------------------------------------------------------------

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "francecentral"
}

variable "supabase_connection_string" {
  description = "Supabase PostgreSQL connection string, injected into the Function App as SUPABASE_CONNECTION_STRING"
  type        = string
  sensitive   = true
}

variable "retention_bronze_days" {
  description = "Bronze layer data retention in days"
  type        = number
  default     = 180
}

variable "retention_silver_days" {
  description = "Silver layer data retention in days"
  type        = number
  default     = 90
}

variable "retention_audit_days" {
  description = "Audit logs retention in days"
  type        = number
  default     = 365
}
