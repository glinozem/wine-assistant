-- db/migrations/0015_ops_daily_import_runs.sql
-- ============================================================
-- Ops Daily Import: runs registry (DB-backed history)
-- Issue: #176
-- Date: 2026-01-xx
-- Depends on: 0014_import_runs.sql (update_updated_at_column())
-- ============================================================

CREATE TABLE IF NOT EXISTS public.ops_daily_import_runs (
  run_id         uuid PRIMARY KEY,

  requested_mode text NOT NULL,          -- 'auto' | 'files'
  selected_mode  text NULL,              -- e.g. 'AUTO_LATEST' | 'MANUAL_LIST'

  status         text NOT NULL,          -- RUNNING | OK | OK_WITH_SKIPS | FAILED | TIMEOUT | ...

  started_at     timestamptz NOT NULL,
  finished_at    timestamptz NULL,
  duration_ms    bigint NULL,

  summary        jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- Full run details payload (same JSON that is stored in FS logs)
  result_json    jsonb NULL,

  -- Optional pointer to filesystem log location (for artifacts/back-compat)
  log_relpath    text NULL,

  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- Keep updated_at in sync (function introduced in 0014_import_runs.sql)
DROP TRIGGER IF EXISTS tr_ops_daily_import_runs_updated_at ON public.ops_daily_import_runs;
CREATE TRIGGER tr_ops_daily_import_runs_updated_at
BEFORE UPDATE ON public.ops_daily_import_runs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Primary “history feed” index (newest first)
CREATE INDEX IF NOT EXISTS ix_ops_daily_import_runs_started_desc
  ON public.ops_daily_import_runs (started_at DESC, run_id DESC);

-- Filtering by status + time window + stable ordering
CREATE INDEX IF NOT EXISTS ix_ops_daily_import_runs_status_started_desc
  ON public.ops_daily_import_runs (status, started_at DESC, run_id DESC);

-- Optional: fast lookup of active runs
CREATE INDEX IF NOT EXISTS ix_ops_daily_import_runs_running
  ON public.ops_daily_import_runs (started_at DESC, run_id DESC)
  WHERE status = 'RUNNING';
