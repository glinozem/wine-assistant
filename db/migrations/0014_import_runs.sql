-- db/migrations/0014_import_runs.sql
-- ============================================================
-- Import Runs: Attempt Journal with Retry Support
-- ============================================================
-- Version: 1.0 PRODUCTION (sanity-checked, ready for merge)
-- Date: 2025-12-23
-- Dependencies: Extends ingest_envelope system
-- ============================================================

-- NOTE: gen_random_uuid() requires pgcrypto extension in PostgreSQL.
-- If pgcrypto is managed centrally, keep this comment only.
-- Otherwise uncomment:
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Helper Function: Auto-update updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_updated_at_column() IS
    'Auto-updates updated_at column on row modification. Reusable trigger function.';

-- ============================================================
-- Main Table: import_runs
-- ============================================================

CREATE TABLE import_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    supplier VARCHAR(100) NOT NULL,
    source_filename TEXT NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    file_size_bytes BIGINT,

    envelope_id UUID NULL REFERENCES ingest_envelope(envelope_id) ON DELETE SET NULL,

    as_of_date DATE NOT NULL,
    as_of_datetime TIMESTAMPTZ,

    status VARCHAR(20) NOT NULL
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped', 'rolled_back'))
        DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    triggered_by VARCHAR(100),
    processing_mode VARCHAR(20) NOT NULL DEFAULT 'atomic'
        CHECK (processing_mode IN ('atomic', 'chunked')),

    total_rows_processed INT DEFAULT 0,
    new_sku_count INT DEFAULT 0,
    updated_sku_count INT DEFAULT 0,
    new_winery_count INT DEFAULT 0,
    quarantine_count INT DEFAULT 0,
    rows_skipped INT DEFAULT 0,

    error_summary TEXT,
    error_details JSONB,

    artifact_paths JSONB,
    import_config JSONB
);

COMMENT ON TABLE import_runs IS
    'Journal of import attempts. Supports retry after failed. Extends ingest_envelope.';

COMMENT ON COLUMN import_runs.envelope_id IS
    'Optional link to ingest_envelope. Set by PR-2 orchestrator for traceability.';

COMMENT ON COLUMN import_runs.status IS
    'pending=created, running=processing, success=done, failed=error, skipped=duplicate, rolled_back=manual fix.';

-- ============================================================
-- Triggers
-- ============================================================

CREATE TRIGGER trg_import_runs_updated_at
    BEFORE UPDATE ON import_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Constraints: Single Blocking Index
-- ============================================================

CREATE UNIQUE INDEX ux_import_runs_blocking_key
    ON import_runs (supplier, file_sha256, as_of_date)
    WHERE status IN ('pending', 'running', 'success');

COMMENT ON INDEX ux_import_runs_blocking_key IS
    'CRITICAL: Blocks concurrent imports, pending after success, duplicate success. Allows retry after failed, multiple skipped. NOTE: Stuck runs (pending/running) block new attempts until resolved (see operational notes).';

-- ============================================================
-- Performance Indexes
-- ============================================================

CREATE INDEX ix_import_runs_supplier_date
    ON import_runs (supplier, as_of_date DESC, created_at DESC);

CREATE INDEX ix_import_runs_status
    ON import_runs (status, created_at DESC)
    WHERE status IN ('running', 'pending', 'failed');

CREATE INDEX ix_import_runs_success_recent
    ON import_runs (supplier, finished_at DESC)
    WHERE status = 'success';

CREATE INDEX ix_import_runs_envelope_id
    ON import_runs (envelope_id)
    WHERE envelope_id IS NOT NULL;

COMMENT ON INDEX ix_import_runs_envelope_id IS
    'Supports joins to ingest_envelope for audit/traceability queries.';

-- ============================================================
-- Views
-- ============================================================

CREATE VIEW v_import_runs_summary AS
SELECT
    run_id,
    supplier,
    source_filename,
    file_sha256,
    as_of_date,
    status,
    started_at,
    finished_at,
    EXTRACT(EPOCH FROM (finished_at - started_at))::NUMERIC(10,2) AS duration_seconds,
    total_rows_processed,
    new_sku_count,
    updated_sku_count,
    quarantine_count,
    error_summary,
    triggered_by,
    created_at
FROM import_runs;

COMMENT ON VIEW v_import_runs_summary IS
    'Import runs with calculated duration. Caller must ORDER BY in query.';

CREATE VIEW v_import_staleness AS
SELECT
    supplier,

    MAX(finished_at) FILTER (WHERE status = 'success') AS last_success_at,
    (MAX(finished_at) FILTER (WHERE status = 'success') IS NOT NULL) AS has_success,

    EXTRACT(EPOCH FROM (
        NOW() - MAX(finished_at) FILTER (WHERE status = 'success')
    )) / 3600 AS hours_since_success,

    COUNT(*) FILTER (
        WHERE status = 'success'
          AND finished_at > NOW() - INTERVAL '7 days'
    ) AS success_count_7d,

    COUNT(*) FILTER (
        WHERE status = 'failed'
          AND finished_at > NOW() - INTERVAL '7 days'
    ) AS failed_count_7d,

    COUNT(*) FILTER (WHERE status = 'running') AS currently_running,

    (ARRAY_AGG(
        error_summary
        ORDER BY COALESCE(finished_at, created_at) DESC
    ) FILTER (
        WHERE status = 'failed'
          AND COALESCE(finished_at, created_at) > NOW() - INTERVAL '7 days'
    ))[1] AS last_error

FROM import_runs
GROUP BY supplier;

COMMENT ON VIEW v_import_staleness IS
    'Data freshness per supplier. Full history. COALESCE handles NULL finished_at. has_success simplifies alerts.';

-- ============================================================
-- Operational Notes: Handling Stuck Runs
-- ============================================================
--
-- DETECTION (example threshold: 2 hours):
--   SELECT run_id, supplier, status, started_at,
--          EXTRACT(EPOCH FROM (NOW() - started_at))/60 AS minutes_running
--   FROM import_runs
--   WHERE status = 'running'
--     AND started_at < NOW() - INTERVAL '2 hours';
--
-- RESOLUTION:
--   UPDATE import_runs
--   SET status = 'rolled_back',
--       error_summary = 'Process crashed or timeout',
--       finished_at = NOW()
--   WHERE run_id = %s
--     AND status IN ('pending', 'running');
--
-- AUTOMATION (PR-2/future):
--   - periodic stale-run detector (e.g., every 15 minutes)
--   - marks stale running/pending as rolled_back and notifies on-call
--

-- ============================================================
-- Rollback Script
-- ============================================================
-- DROP VIEW IF EXISTS v_import_staleness CASCADE;
-- DROP VIEW IF EXISTS v_import_runs_summary CASCADE;
-- DROP TABLE IF EXISTS import_runs CASCADE;
-- DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
