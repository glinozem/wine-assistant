-- 0009_schema-migrations-view-fix.sql
-- Витрина со списком миграций (версия, имя, checksum, UTC и MSK)

DROP VIEW IF EXISTS public.schema_migrations_view;

CREATE OR REPLACE VIEW public.schema_migrations_view AS
SELECT
  split_part(filename, '_' ,1)                AS version,
  filename,
  sha256                                      AS checksum,
  applied_at,
  (applied_at AT TIME ZONE 'Europe/Moscow')   AS applied_msk
FROM public.schema_migrations
ORDER BY applied_at DESC;
