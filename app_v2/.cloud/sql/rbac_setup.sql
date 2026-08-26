-- ============================================================================
-- RBAC Setup — Story 3.2, Task 3
-- Configures read-only access for API service principal on Gold tables
-- ============================================================================

-- Create read-only role for API consumers (NFR-S3)
CREATE ROLE gold_reader;

-- Grant SELECT-only on Gold tables
GRANT SELECT ON DIM_REGION TO gold_reader;
GRANT SELECT ON DIM_TIME TO gold_reader;
GRANT SELECT ON DIM_SOURCE TO gold_reader;
GRANT SELECT ON FACT_ENERGY_FLOW TO gold_reader;

-- Deny all write operations to gold_reader
DENY INSERT, UPDATE, DELETE ON DIM_REGION TO gold_reader;
DENY INSERT, UPDATE, DELETE ON DIM_TIME TO gold_reader;
DENY INSERT, UPDATE, DELETE ON DIM_SOURCE TO gold_reader;
DENY INSERT, UPDATE, DELETE ON FACT_ENERGY_FLOW TO gold_reader;

-- Create ETL writer role (used by Azure Function Managed Identity)
CREATE ROLE gold_writer;

GRANT SELECT, INSERT, UPDATE ON DIM_REGION TO gold_writer;
GRANT SELECT, INSERT, UPDATE ON DIM_TIME TO gold_writer;
GRANT SELECT, INSERT, UPDATE ON DIM_SOURCE TO gold_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON FACT_ENERGY_FLOW TO gold_writer;

-- Usage:
-- ALTER ROLE gold_reader ADD MEMBER [api-service-principal];
-- ALTER ROLE gold_writer ADD MEMBER [func-app-managed-identity];
