-- ============================================================================
-- Migration 001: Asset Lifecycle Management — Story 1.3
-- Extends DIM_REGION with lifecycle tracking columns
-- ============================================================================

-- Add lifecycle columns to DIM_REGION
-- Soft-delete pattern: status transitions active → stale → inactive
-- No DELETE statements — preserves historical referential integrity

ALTER TABLE DIM_REGION ADD
    status VARCHAR(10) NOT NULL DEFAULT 'active',       -- active | stale | inactive
    first_seen_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    last_seen_at DATETIME2 NOT NULL DEFAULT GETDATE();

-- Update existing rows to active with current timestamp
UPDATE DIM_REGION
SET status = 'active',
    first_seen_at = GETDATE(),
    last_seen_at = GETDATE()
WHERE status IS NULL OR status = '';

-- Index for staleness queries
CREATE INDEX IX_DIM_REGION_status_last_seen
ON DIM_REGION (status, last_seen_at);
