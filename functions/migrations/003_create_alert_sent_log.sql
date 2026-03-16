-- Migration 003: Create ALERT_SENT_LOG table
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)
-- Requires: 001_create_user_account.sql executed first

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='ALERT_SENT_LOG')
    CREATE TABLE ALERT_SENT_LOG (
        id          INT             PRIMARY KEY IDENTITY(1,1),
        user_id     INT             NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
        region_code NVARCHAR(10)    NOT NULL,
        alert_type  NVARCHAR(50)    NOT NULL,
        sent_at     DATETIME2       NOT NULL DEFAULT GETUTCDATE()
    );

-- Deduplication constraint: max 1 alert per user/region/type per calendar day
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='UQ_ALERT_SENT_LOG_daily')
    CREATE UNIQUE INDEX UQ_ALERT_SENT_LOG_daily
    ON ALERT_SENT_LOG (user_id, region_code, alert_type, CAST(sent_at AS DATE));
