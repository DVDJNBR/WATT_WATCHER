-- Migration 002: Create ALERT_SUBSCRIPTION table
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)
-- Requires: 001_create_user_account.sql executed first

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='ALERT_SUBSCRIPTION')
    CREATE TABLE ALERT_SUBSCRIPTION (
        id          INT             PRIMARY KEY IDENTITY(1,1),
        user_id     INT             NOT NULL REFERENCES USER_ACCOUNT(id) ON DELETE CASCADE,
        region_code NVARCHAR(10)    NOT NULL,
        alert_type  NVARCHAR(50)    NOT NULL,  -- 'under_production' | 'over_production'
        is_active   BIT             NOT NULL DEFAULT 1,
        created_at  DATETIME2       NOT NULL DEFAULT GETUTCDATE()
    );

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_ALERT_SUBSCRIPTION_user_region')
    CREATE INDEX IX_ALERT_SUBSCRIPTION_user_region ON ALERT_SUBSCRIPTION (user_id, region_code);
