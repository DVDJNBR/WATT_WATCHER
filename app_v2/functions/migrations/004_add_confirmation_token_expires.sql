-- Migration 004: Add confirmation_token_expires to USER_ACCOUNT
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'USER_ACCOUNT'
      AND COLUMN_NAME = 'confirmation_token_expires'
)
    ALTER TABLE USER_ACCOUNT
    ADD confirmation_token_expires DATETIME2 NULL;
