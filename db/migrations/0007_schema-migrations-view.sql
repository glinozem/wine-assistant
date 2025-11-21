-- 0007_schema-migrations-view.sql
-- Создаёт удобный VIEW для просмотра применённых миграций

CREATE OR REPLACE VIEW public.schema_migrations_recent AS
SELECT split_part(filename, '_', 1) AS version,
       filename,
       sha256 AS checksum,
       applied_at
FROM public.schema_migrations
ORDER BY applied_at DESC;
