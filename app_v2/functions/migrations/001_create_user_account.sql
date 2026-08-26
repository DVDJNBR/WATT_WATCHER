-- Migration 001: Create USER_ACCOUNT table
-- Idempotent: safe to run multiple times
-- Target: Azure SQL (SQL Server)

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='USER_ACCOUNT')
    CREATE TABLE USER_ACCOUNT (
        id                  INT             PRIMARY KEY IDENTITY(1,1),
        email               NVARCHAR(255)   NOT NULL UNIQUE,
        password_hash       NVARCHAR(255)   NOT NULL,
        is_confirmed        BIT             NOT NULL DEFAULT 0,
        confirmation_token  NVARCHAR(500)   NULL,
        reset_token         NVARCHAR(500)   NULL,
        reset_token_expires DATETIME2       NULL,
        last_activity       DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE()
    );

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_USER_ACCOUNT_email')
    CREATE INDEX IX_USER_ACCOUNT_email ON USER_ACCOUNT (email);
