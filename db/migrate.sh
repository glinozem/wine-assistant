#!/usr/bin/env bash
set -euo pipefail

echo "[migrator] wait for DB..."

: "${DB_HOST:?missing DB_HOST}"
: "${DB_PORT:?missing DB_PORT}"
: "${DB_USER:?missing DB_USER}"
: "${DB_PASSWORD:?missing DB_PASSWORD}"
: "${DB_NAME:?missing DB_NAME}"

export PGPASSWORD="${DB_PASSWORD}"

# Ждём доступности инстанса
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
  sleep 1
done
echo " ok"

PSQL=(psql -v ON_ERROR_STOP=1 -q -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}")

apply_sql() {
  local file="$1"
  echo "[migrator] -> ${file}"
  "${PSQL[@]}" -f "${file}"
}

record_migration_table_safe() {
  # На случай, если 0000 не создаст таблицу по какой-то причине — создадим «страховочную».
  "${PSQL[@]}" -c '
    CREATE TABLE IF NOT EXISTS public.schema_migrations (
      id          bigserial PRIMARY KEY,
      filename    text UNIQUE NOT NULL,
      sha256      text NOT NULL,
      applied_at  timestamptz NOT NULL DEFAULT now()
    );
  '
}

record_migration() {
  local file="$1"
  local filename sha
  filename="$(basename "${file}")"
  sha="$(sha256sum "${file}" | awk "{print \$1}")"
  "${PSQL[@]}" -c "
    INSERT INTO public.schema_migrations (filename, sha256, applied_at)
    VALUES ('${filename}', '${sha}', now())
    ON CONFLICT (filename) DO NOTHING;
  "
  echo "[migrator]    recorded ${filename} (${sha})"
}

echo "[migrator] apply init.sql"
apply_sql "/migrations/init.sql"

echo "[migrator] apply migrations..."
record_migration_table_safe

# Проходим по файлам; если каталог пуст — ничего страшного
found=0
for f in /migrations/migrations/*.sql; do
  [ -e "$f" ] || continue
  found=1
  apply_sql "$f"
  record_migration "$f"
done

if [ "$found" -eq 0 ]; then
  echo "[migrator] no migration files found in /migrations/migrations"
fi

echo "[migrator] done."
