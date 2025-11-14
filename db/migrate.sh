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
DB_USER="${DB_USER:-${PGUSER:-postgres}}"
DB_PASSWORD="${DB_PASSWORD:-${PGPASSWORD:-postgres}}"
DB_NAME="${DB_NAME:-${PGDATABASE:-wine_db}}"

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

# --- 4) Проверяем инструменты ---
command -v psql >/dev/null 2>&1 || { echo "[migrator] psql not found"; exit 127; }
command -v pg_isready >/dev/null 2>&1 || { echo "[migrator] pg_isready not found"; exit 127; }

# --- 5) Ждём БД (с таймаутом) ---
TIMEOUT_SEC="${TIMEOUT_SEC:-90}"
echo "[migrator] wait for DB at ${DB_HOST}:${DB_PORT} (user=${DB_USER}, db=${DB_NAME}) with timeout ${TIMEOUT_SEC}s..."
for ((i=1; i<=TIMEOUT_SEC; i++)); do
  if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; then
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

PSQL=(psql -v ON_ERROR_STOP=1 -q -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}")

apply_sql() {
  local file="$1"
  echo "[migrator] -> ${file}"
  "${PSQL[@]}" -f "${file}"
}

record_migration_table_safe() {
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
  if command -v sha256sum >/dev/null 2>&1; then
    sha="$(sha256sum "${file}" | awk '{print $1}')"
  else
    sha="$(shasum -a 256 "${file}" | awk '{print $1}')"
  fi
  "${PSQL[@]}" -c "
    INSERT INTO public.schema_migrations (filename, sha256, applied_at)
    VALUES ('${filename}', '${sha}', now())
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

echo "[migrator] apply migrations..."
record_migration_table_safe

found=0
if [[ -d "${MIGR_DIR}" ]]; then
  shopt -s nullglob
  for f in "${MIGR_DIR}"/*.sql; do
    found=1
    apply_sql "$f"
    record_migration "$f"
  done
  shopt -u nullglob
fi

if [[ "$found" -eq 0 ]]; then
  echo "[migrator] no migration files found in ${MIGR_DIR}"
fi

echo "[migrator] done."
