-- Migration 005: Add inactivity_warning_sent_at to USER_ACCOUNT
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)
-- Used by the daily RGPD cleanup timer (Story 6.1) to track when the 30-day warning was sent.

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'USER_ACCOUNT'
      AND COLUMN_NAME = 'inactivity_warning_sent_at'
)
    ALTER TABLE USER_ACCOUNT
    ADD inactivity_warning_sent_at DATETIME2 NULL;
