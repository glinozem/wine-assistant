#!/usr/bin/env bash
set -euo pipefail

# --- CONFIG (можно переопределить переменными среды) ---
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-15432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-wine_db}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-db/migrations}"
TZ_VIEW="${TZ_VIEW:-Europe/Moscow}"   # для столбца applied_msk в вью

# --- Определяем docker compose команду (или отсутствие) ---
detect_compose() {
  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      echo "docker compose"
      return
    elif command -v docker-compose >/dev/null 2>&1; then
      echo "docker-compose"
      return
    fi
  fi
  echo ""  # нет docker compose — будем использовать локальный psql
}

COMPOSE_CMD="$(detect_compose)"

# --- Хелперы для psql ---
psql_exec() {
  # Используем docker compose exec -T db psql, если доступно; иначе локальный psql
  if [[ -n "$COMPOSE_CMD" ]]; then
    $COMPOSE_CMD exec -T db psql -v ON_ERROR_STOP=1 -X -q -U "$PGUSER" -d "$PGDATABASE" "$@"
  else
    PGPASSWORD="${PGPASSWORD:-}" psql -v ON_ERROR_STOP=1 -X -q \
      -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" "$@"
  fi
}

pg_isready_wait() {
  echo "Waiting for Postgres readiness..."
  for i in {1..90}; do
    if [[ -n "$COMPOSE_CMD" ]]; then
      if $COMPOSE_CMD exec -T db pg_isready -U "$PGUSER" -d "$PGDATABASE" -h localhost -p 5432 >/dev/null 2>&1; then
        return 0
      fi
    else
      if pg_isready -U "$PGUSER" -d "$PGDATABASE" -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
  done
  echo "ERROR: Postgres is not ready in time." >&2
  return 1
}

sha256_file() {
  # Кросс-платформенный sha256: Linux (sha256sum) / macOS (shasum -a 256)
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# --- Поднимаем БД (если docker compose доступен) ---
if [[ -n "$COMPOSE_CMD" ]]; then
  $COMPOSE_CMD up -d db
fi

# --- Ждём готовности БД ---
pg_isready_wait

# --- Базовые расширения + реестр миграций ---
psql_exec <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.schema_migrations(
  filename   text PRIMARY KEY,
  sha256     char(64),
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

# --- Применяем миграции по порядку ---
if [[ ! -d "$MIGRATIONS_DIR" ]]; then
  echo "WARN: Migrations dir not found: $MIGRATIONS_DIR — пропускаю."
  exit 0
fi

shopt -s nullglob
mapfile -t FILES < <(ls -1 "$MIGRATIONS_DIR"/*.sql | sort)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "WARN: No *.sql files found in $MIGRATIONS_DIR — нечего применять."
else
  for f in "${FILES[@]}"; do
    name="$(basename "$f")"
    hash="$(sha256_file "$f")"

    # Узнаем, зарегистрирована ли миграция и какой checksum
    current_sha="$(psql_exec -Atc "SELECT sha256 FROM public.schema_migrations WHERE filename='${name}'" || true)"

    if [[ -n "$current_sha" ]]; then
      if [[ "$current_sha" == "$hash" ]]; then
        echo ">> SKIP $name (already applied)"
        continue
      else
        echo "ERROR: Migration $name already recorded with another checksum!"
        echo "       recorded: $current_sha"
        echo "       current : $hash"
        exit 1
      fi
    fi

    echo ">> Applying $name"
    # Важно: не \i; внутри контейнера нет доступа к host-файлу — читаем через stdin
    psql_exec < "$f"

    # Регистрируем факт применения
    psql_exec -c "INSERT INTO public.schema_migrations(filename, sha256)
                  VALUES ('${name}', '${hash}')
                  ON CONFLICT (filename) DO UPDATE
                  SET sha256 = EXCLUDED.sha256,
                      applied_at = now();"
  done
fi

# --- Обновляем VIEW со списком миграций (и столбцом checksum) ---
psql_exec <<SQL
CREATE OR REPLACE VIEW public.schema_migrations_recent AS
SELECT split_part(filename, '_', 1) AS version,
       filename,
       sha256 AS checksum,
       applied_at,
       applied_at AT TIME ZONE '${TZ_VIEW}' AS applied_msk
FROM public.schema_migrations
ORDER BY applied_at DESC;
SQL

# --- Показать последние применённые миграции ---
echo
echo "=== Recent migrations ==="
psql_exec -c "SELECT version, filename, checksum, applied_at, applied_msk
              FROM public.schema_migrations_recent
              ORDER BY applied_at DESC
              LIMIT 8;"

echo
echo "All migrations applied."
