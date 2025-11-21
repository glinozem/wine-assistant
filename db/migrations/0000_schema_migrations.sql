-- 0000_schema_migrations.sql
-- Creates a tiny registry to record applied migrations and common extensions.
-- Idempotent: safe to re-run.
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram search
CREATE EXTENSION IF NOT EXISTS vector;     -- optional; safe if extension exists

CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename   text PRIMARY KEY,
  sha256     char(64),
  applied_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.schema_migrations IS 'Simple registry of applied SQL migrations';
