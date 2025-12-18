#!/usr/bin/env bash
set -Eeuo pipefail

# --- 1) Загружаем .env при отсутствии переменных ---
ENV_FILE="${ENV_FILE:-.env}"
if [[ -z "${DB_HOST:-}" && -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE"
  set +a
fi

# --- 2) Нормализуем вход: DB_* > PG_* > defaults ---
DB_HOST="${DB_HOST:-${PGHOST:-127.0.0.1}}"
DB_PORT="${DB_PORT:-${PGPORT:-5432}}"
DB_USER="${DB_USER:-${PGUSER:-${POSTGRES_USER:-postgres}}}"
DB_PASSWORD="${DB_PASSWORD:-${PGPASSWORD:-${POSTGRES_PASSWORD:-postgres}}}"
DB_NAME="${DB_NAME:-${PGDATABASE:-${POSTGRES_DB:-wine_db}}}"

export PGPASSWORD="${DB_PASSWORD}"

# --- 3) Где лежат миграции ---
MIGRATIONS_ROOT="${MIGRATIONS_ROOT:-/migrations}"
if [[ ! -d "$MIGRATIONS_ROOT" ]]; then
  for d in "./db" "./migrations"; do
    if [[ -d "$d" ]]; then MIGRATIONS_ROOT="$d"; break; fi
  done
fi
INIT_SQL="${MIGRATIONS_ROOT}/init.sql"
MIGR_DIR="${MIGRATIONS_ROOT}/migrations"

if [[ ! -d "${MIGR_DIR}" ]]; then
  echo "[migrator] ERROR: migrations dir not found: ${MIGR_DIR}"
  exit 2
fi

# --- 4) Проверяем инструменты ---
command -v psql >/dev/null 2>&1 || { echo "[migrator] psql not found"; exit 127; }
command -v pg_isready >/dev/null 2>&1 || { echo "[migrator] pg_isready not found"; exit 127; }

# --- 5) Ждём БД (с таймаутом) ---
TIMEOUT_SEC="${TIMEOUT_SEC:-120}"
echo "[migrator] wait for DB at ${DB_HOST}:${DB_PORT} (user=${DB_USER}, db=${DB_NAME}) with timeout ${TIMEOUT_SEC}s..."
for ((i=1; i<=TIMEOUT_SEC; i++)); do
  if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
    echo " ok"
    break
  fi
  sleep 1
  if (( i % 10 == 0 )); then echo "[migrator] still waiting... (${i}s)"; fi
  if (( i == TIMEOUT_SEC )); then
    echo "[migrator] ERROR: DB not ready after ${TIMEOUT_SEC}s"
    exit 124
  fi
done

PSQL=(psql -X -v ON_ERROR_STOP=1 -q -h "${DB_HOST}" -p "${DB_PORT}" -U
"${DB_USER}" -d "${DB_NAME}")

apply_sql() {
  local file="$1"
  echo "[migrator] -> ${file}"
  "${PSQL[@]}" -f "${file}"
}

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  else
    shasum -a 256 "$file" | awk '{print $1}'
  fi
}

record_migration_table_safe() {
  "${PSQL[@]}" -c '
    CREATE TABLE IF NOT EXISTS public.schema_migrations (
      id          bigserial PRIMARY KEY,
      filename    text UNIQUE NOT NULL,
      sha256      text NOT NULL,
      applied_at  timestamptz NOT NULL DEFAULT now()
    );

    -- На случай если таблица была создана ранее без UNIQUE по filename
    CREATE UNIQUE INDEX IF NOT EXISTS ux_schema_migrations_filename
      ON public.schema_migrations (filename);
  '
}

sql_escape_literal() {
  # экранируем одинарные кавычки для SQL-литерала
  printf "%s" "$1" | sed "s/'/''/g"
}

record_migration() {
  local file="$1"
  local filename sha filename_escaped sha_escaped

  filename="$(basename "${file}")"
  sha="$(sha256_file "$file")"

  filename_escaped="$(sql_escape_literal "$filename")"
  sha_escaped="$(sql_escape_literal "$sha")"

  "${PSQL[@]}" -c "
    INSERT INTO public.schema_migrations (filename, sha256, applied_at)
    VALUES ('${filename_escaped}', '${sha_escaped}', now())
    ON CONFLICT (filename) DO NOTHING;
  "
  echo "[migrator]    recorded ${filename} (${sha})"
}


# --- 6) Применяем init + миграции ---
if [[ -f "${INIT_SQL}" ]]; then
  echo "[migrator] apply init.sql"
  apply_sql "${INIT_SQL}"
else
  echo "[migrator] WARNING: ${INIT_SQL} not found, skipping init.sql"
fi

record_migration_table_safe

applied_sha() {
  local filename_escaped
  filename_escaped="$(sql_escape_literal "$1")"
  "${PSQL[@]}" -tA -c \
  "SELECT sha256
   FROM public.schema_migrations
   WHERE filename='${filename_escaped}'
   ORDER BY applied_at DESC
   LIMIT 1;" 2>/dev/null | tr -d '[:space:]' || true
}

echo "[migrator] apply migrations..."
found=0

# ВАЖНО:
# - применяем только миграции формата 0000_*.sql, 0013_*.sql и т.п.
# - это автоматически исключает ваши 2025-10-14-*.sql (там после 4 цифр идёт '-', а не '_')
for f in "${MIGR_DIR}"/[0-9][0-9][0-9][0-9]_*.sql; do
  [ -e "$f" ] || continue
  found=1

  base="$(basename "$f")"
  sha_now="$(sha256_file "$f")"
  sha_db="$(applied_sha "$base")"

  if [ -n "$sha_db" ]; then
    if [ "$sha_db" != "$sha_now" ]; then
      echo "[migrator] ERROR: migration ${base} already applied with sha=${sha_db}, but local file sha=${sha_now}. Do not edit applied migrations."
      exit 4
    fi
    echo "[migrator] skip ${base} (already applied)"
    continue
  fi

  apply_sql "$f"
  record_migration "$f"
done

if [ "${found}" -eq 0 ]; then
  echo "[migrator] no migrations found in ${MIGR_DIR} (pattern: [0-9][0-9][0-9][0-9]_*.sql)"
fi

echo "[migrator] done."
