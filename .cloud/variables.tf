# -----------------------------------------------------------------------------
# GRID_POWER_STREAM — Input Variables
# -----------------------------------------------------------------------------

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "francecentral"
}

variable "sql_admin_login" {
  description = "SQL Server administrator login"
  type        = string
  default     = "wwadmin"
}

variable "sql_admin_password" {
  description = "SQL Server administrator password"
  type        = string
  sensitive   = true
}

variable "sql_auto_pause_delay" {
  description = "Minutes of inactivity before SQL auto-pause (-1 to disable)"
  type        = number
  default     = -1
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
