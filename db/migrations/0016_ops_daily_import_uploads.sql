-- db/migrations/0016_ops_daily_import_uploads.sql
-- ============================================================
-- Ops Daily Import: inbox uploads registry (SHA-256 dedupe source of truth)
-- Issue: #175
-- Date: 2026-01-xx
-- Depends on: 0014_import_runs.sql (update_updated_at_column())
-- ============================================================

CREATE TABLE IF NOT EXISTS public.ops_daily_import_uploads (
  upload_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Dedupe scope: only within active INBOX
  status         text NOT NULL DEFAULT 'INBOX'
    CHECK (status IN ('INBOX', 'ARCHIVED', 'QUARANTINED', 'DELETED')),

  original_name  text NOT NULL,         -- user-provided filename
  saved_name     text NOT NULL,         -- filesystem name inside INBOX

  -- Truth: content fingerprint
  sha256         char(64) NOT NULL,
  size_bytes     bigint NOT NULL CHECK (size_bytes >= 0),

  uploaded_at    timestamptz NOT NULL DEFAULT now(),
  moved_at       timestamptz NULL,

  -- Future linkage: which run consumed this upload
  consumed_run_id uuid NULL
    REFERENCES public.ops_daily_import_runs(run_id) ON DELETE SET NULL,

  metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,

  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- Keep updated_at in sync (function introduced in 0014_import_runs.sql)
DROP TRIGGER IF EXISTS tr_ops_daily_import_uploads_updated_at ON public.ops_daily_import_uploads;
CREATE TRIGGER tr_ops_daily_import_uploads_updated_at
BEFORE UPDATE ON public.ops_daily_import_uploads
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =========================
-- Uniqueness / indexes
-- =========================

-- Truth: one content (sha256) can exist only once in active inbox
CREATE UNIQUE INDEX IF NOT EXISTS ux_ops_di_uploads_inbox_sha256
  ON public.ops_daily_import_uploads (sha256)
  WHERE status = 'INBOX';

-- Prevent name collisions in active inbox (aligns with FS allocator)
CREATE UNIQUE INDEX IF NOT EXISTS ux_ops_di_uploads_inbox_saved_name
  ON public.ops_daily_import_uploads (saved_name)
  WHERE status = 'INBOX';

-- Common read patterns (newest first)
CREATE INDEX IF NOT EXISTS ix_ops_di_uploads_uploaded_desc
  ON public.ops_daily_import_uploads (uploaded_at DESC, upload_id DESC);

CREATE INDEX IF NOT EXISTS ix_ops_di_uploads_status_uploaded_desc
  ON public.ops_daily_import_uploads (status, uploaded_at DESC, upload_id DESC);

CREATE INDEX IF NOT EXISTS ix_ops_di_uploads_consumed_run_id
  ON public.ops_daily_import_uploads (consumed_run_id)
  WHERE consumed_run_id IS NOT NULL;

COMMENT ON TABLE public.ops_daily_import_uploads IS
  'Ops Daily Import uploads registry. Dedupe truth: sha256. Enforced only for INBOX via partial unique index.';
