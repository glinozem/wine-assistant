# Wine Assistant — API & ETL

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/test.yml/badge.svg)](../../actions/workflows/test.yml)
![Coverage](https://img.shields.io/badge/coverage-61%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![Postgres](https://img.shields.io/badge/PostgreSQL-16.x-blue)
![License](https://img.shields.io/badge/license-MIT-informational)

Проект для загрузки прайс‑листов, нормализации данных, дедупликации и отдачи агрегированного API поверх PostgreSQL.
Поддерживает идемпотентную обработку входных файлов, хранение истории цен, поиск, health‑пробы и готовое локальное окружение в Docker.

---

## Содержание

- [Что нового](#что-нового)
- [Быстрый старт](#быстрый-старт)
- [API: эндпоинты и Swagger](#api-эндпоинты-и-swagger)
- [ETL: загрузка прайсов](#etl-загрузка-прайсов)
- [Переменные окружения](#переменные-окружения)
- [Docker Compose (полный)](#docker-compose-полный)
- [Фрагменты кода (apppy, миграции)](#фрагменты-кода-apppy-миграции)
- [Как поднимается БД в CI](#как-поднимается-бд-в-ci)
- [Миграции и схема](#миграции-и-схема)
- [Тесты и покрытие](#тесты-и-покрытие)
- [Траблшутинг](#траблшутинг)

---

## Что нового

- **CI:** Postgres 14 на `15432` + readiness (в локальном Docker — Postgres 16 + pgvector).
- **CI:** Автозагрузка схем (idempotency + products/inventory) и запуск миграций перед тестами.
- **Тесты:** стабилизация `upsert_records()` в CI, проверка индексов и таблиц на `/ready`.
- **Документация:** пример Swagger docstrings, мини OpenAPI‑файл, обновлённый README с разделом про CI‑БД.

_Фоллоуапы — отдельными PR при необходимости._

---

## Быстрый старт

```bash
# 1) Локально запустить стек
docker compose up -d

# 2) Проверить готовность
curl -s http://127.0.0.1:18000/live  | python -m json.tool
curl -s http://127.0.0.1:18000/ready | python -m json.tool

# 3) Открыть Adminer
# http://127.0.0.1:18080  (System: PostgreSQL; Server: db; User: postgres; Pass: dev_local_pw; DB: wine_db)

# 4) (опционально) прогнать миграции принудительно
pwsh ./db/migrate.ps1
# либо под Linux/macOS
bash  ./db/migrate.sh
```

**Порты по умолчанию**
- API: `127.0.0.1:18000`
- DB:  `127.0.0.1:15432` (наружу), внутри сети — `db:5432`
- Adminer: `127.0.0.1:18080`

---

## API: эндпоинты и Swagger

### Базовые проверки
- `GET /live` — liveness probe
- `GET /ready` — readiness + быстрые проверки таблиц/индексов
- `GET /version` — версия сервиса

### Каталог, цены, остатки (V1)
- `GET /v1/products/search?query={text}&limit=20` — поиск по каталогу (ILIKE + триграммы).
- `GET /v1/products/{code}` — карточка товара (каталог).
- `GET /v1/prices/{code}` — текущая цена и/или история цен.
- `GET /v1/inventory/{code}` — складские остатки.

> Реальные эндпоинты могут отличаться — ориентируйся по текущему `api/app.py` в репозитории.

### Пример Swagger‑docstring (Flasgger‑стиль) в `api/app.py`

```python
@app.get("/live")
def live():
    \"\"\"
    Liveness probe
    ---
    tags: [Health]
    summary: Проба живости
    responses:
      200:
        description: Сервис жив
        examples:
          application/json:
            status: alive
            version: 0.3.0
    \"\"\"
    return jsonify({"status": "alive", "version": VERSION, "uptime_seconds": get_uptime()}), 200
```

```python
@app.get("/v1/products/<string:code>")
def get_product(code: str):
    \"\"\"
    Получить карточку товара
    ---
    tags: [Products]
    parameters:
      - in: path
        name: code
        required: true
        schema:
          type: string
        description: SKU / внутренний код
    responses:
      200:
        description: ОК
        content:
          application/json:
            example:
              code: "TEST001"
              title_ru: "Пример товара"
              country: "France"
              price_final_rub: 1590.0
      404:
        description: Не найдено
    \"\"\"
    ...
```

### Мини‑OpenAPI (фрагмент)

```yaml
openapi: 3.0.3
info:
  title: Wine Assistant API
  version: "0.3.0"
paths:
  /live:
    get:
      tags: [Health]
      summary: Liveness probe
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  status: { type: string }
                  version: { type: string }
  /v1/products/{code}:
    get:
      tags: [Products]
      summary: Карточка товара
      parameters:
        - in: path
          name: code
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
        "404":
          description: Not Found
```

---

## ETL: загрузка прайсов

ETL реализован в `scripts/`:
- `load_csv.py` — универсальная точка входа (CSV/XLSX, авто‑дата по файлу/ячейке, контроль идемпотентности).
- `load_utils.py` — нормализация значений, агрегации и UPSERT в `products`, `inventory`, `product_prices`.
- `idempotency.py` — SHA‑256 файла, `envelopes` и `price_list_entries` (дедупликация входов).
- `date_extraction.py` — поиск даты в A1/B1 Excel, имени файла, тексте; валидация «не из будущего».

### Примеры запуска

```bash
# Загрузка Excel/CSV с прайсом
python scripts/load_csv.py --file ./data/price_2025-11-06.xlsx --asof 2025-11-06

# Жёстко задать скидку из S5 (если есть), а не из файла
PREFER_S5=true python scripts/load_csv.py --file ./data/price.xlsx

# Пропустить файл как дубликат
python scripts/load_csv.py --file ./data/price.xlsx --skip-duplicates
```

Основные таблицы:
- `products(code PK, ... price_list_rub, price_final_rub, price_rub)`
- `product_prices(code, effective_from, effective_to, price_rub, ...)`
- `inventory(code, stock_total, reserved, stock_free, asof_date)`
- `inventory_history(code, changed_at, stock_total, reserved, stock_free)`

Индексы для поиска и аналитики включены миграциями (см. ниже).

---

## Переменные окружения

| Имя            | Назначение                                   | По умолчанию (Docker) |
|----------------|-----------------------------------------------|-----------------------|
| `PGHOST`       | Хост БД                                       | `db`                  |
| `PGPORT`       | Порт БД                                       | `5432`                |
| `PGUSER`       | Пользователь БД                               | `postgres`            |
| `PGPASSWORD`   | Пароль                                        | `dev_local_pw`        |
| `PGDATABASE`   | Имя базы                                      | `wine_db`             |
| `PREFER_S5`    | Брать скидку из S5 (Excel) в приоритете       | `false`               |
| `API_PORT`     | Порт Flask‑приложения внутри контейнера       | `8000`                |
| `TZ`           | Таймзона                                      | `Europe/Moscow`       |

> Для локального запуска вне Docker можно использовать файл `.env` (см. `.env.example`).

---

## Docker Compose (полный)

> **Важно:** `version` в Compose больше не нужен — удалён. Таймзона выставлена в `Europe/Moscow`.

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: wine-assistant-db-1
    environment:
      POSTGRES_DB: wine_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: dev_local_pw
      TZ: Europe/Moscow
    ports:
      - "127.0.0.1:15432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d wine_db -h localhost -p 5432"]
      interval: 3s
      timeout: 2s
      retries: 20

  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: wine-assistant-api:latest
    container_name: wine-assistant-api-1
    command: python -m api.app
    environment:
      FLASK_ENV: development
      API_PORT: "8000"
      PGHOST: db
      PGPORT: "5432"
      PGUSER: postgres
      PGPASSWORD: dev_local_pw
      PGDATABASE: wine_db
      TZ: Europe/Moscow
    ports:
      - "127.0.0.1:18000:8000"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/live || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 30

  adminer:
    image: adminer:4
    container_name: wine-assistant-adminer-1
    environment:
      - TZ=Europe/Moscow
    ports:
      - "127.0.0.1:18080:8080"
    depends_on:
      - db

volumes:
  db_data:
```

### Dockerfile (фрагмент)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY scripts/ ./scripts/
COPY db/ ./db/
COPY .env.example .env

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "-m", "api.app"]
```

---

## Фрагменты кода (app.py, миграции)

### `api/app.py` — Health/Ready/Version (с докстрингами)

```python
from flask import Flask, jsonify
from api.logging_config import setup_logging
from api.request_middleware import before_request, after_request
from scripts.load_utils import get_conn

VERSION = "0.3.0"
app = Flask(__name__)
setup_logging(app)
app.before_request(before_request)
app.after_request(after_request)

@app.get("/live")
def live():
    \"\"\"
    Liveness probe
    ---
    tags: [Health]
    summary: Проба живости
    responses:
      200:
        description: Сервис жив
    \"\"\"
    return jsonify({"status": "alive", "version": VERSION, "uptime_seconds": 0.0}), 200

@app.get("/ready")
def ready():
    \"\"\"
    Readiness probe (+проверки схемы)
    ---
    tags: [Health]
    summary: Готовность сервиса
    responses:
      200:
        description: OK
    \"\"\"
    checks = {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(\"\"\"
          SELECT
            to_regclass('public.products') IS NOT NULL AS products,
            to_regclass('public.product_prices') IS NOT NULL AS product_prices,
            to_regclass('public.inventory') IS NOT NULL AS inventory,
            to_regclass('public.inventory_history') IS NOT NULL AS inventory_history
        \"\"\")
        row = cur.fetchone()
        checks["database"] = {
          "tables": {
            "products": row[0], "product_prices": row[1],
            "inventory": row[2], "inventory_history": row[3]
          },
          "ok": all(row)
        }
    return jsonify({"status": "ready", "checks": checks, "version": VERSION}), 200

@app.get("/version")
def version():
    \"\"\"
    Версия API
    ---
    tags: [Health]
    summary: Версия сервиса
    responses:
      200:
        description: Версия
    \"\"\"
    return jsonify({"version": VERSION}), 200
```

### `db/migrate.ps1` (Windows, PowerShell) — сокращённая версия

> Полная версия лежит в `db/migrate.ps1`. Ниже — та же логика в компактном виде.

```powershell
param([switch]$StartDb)

function Info($m){ Write-Host $m -ForegroundColor Cyan }
function Warn($m){ Write-Host $m -ForegroundColor Yellow }
function Err ($m){ Write-Host $m -ForegroundColor Red }

$PGHOST     = $env:PGHOST     ? $env:PGHOST     : "localhost"
$PGPORT     = $env:PGPORT     ? $env:PGPORT     : "15432"
$PGUSER     = $env:PGUSER     ? $env:PGUSER     : "postgres"
$PGPASSWORD = $env:PGPASSWORD ? $env:PGPASSWORD : "dev_local_pw"
$PGDATABASE = $env:PGDATABASE ? $env:PGDATABASE : "wine_db"

if ($StartDb) { docker compose up -d db | Out-Null }

Info "Waiting for Postgres readiness..."
$ready = $false; 1..60 | ForEach-Object {
  $out = docker compose exec -T db pg_isready -U $PGUSER -d $PGDATABASE -h localhost -p 5432 2>$null
  if ($LASTEXITCODE -eq 0 -or "$out" -match "accepting connections") { $ready = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ready) { Err "DB is not ready"; exit 1 }

# Базовая таблица миграций и расширения
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c @"
CREATE TABLE IF NOT EXISTS public.schema_migrations(
  filename   text PRIMARY KEY,
  sha256     char(64),
  applied_at timestamptz NOT NULL DEFAULT now()
);
"@

# Применение *.sql
$migrations = Get-ChildItem -Path "./db/migrations" -Filter "*.sql" | Sort-Object Name
foreach ($f in $migrations) {
  $name = $f.Name
  $hash = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash.ToLower()
  $exists = docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -A -t -c "SELECT 1 FROM public.schema_migrations WHERE filename='$name' LIMIT 1;"

  if ($exists.Trim() -eq "1") {
    Info ">> SKIP $name (already applied)"
    continue
  }
  Info ">> Applying $name"
  docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -f "/docker-entrypoint-initdb.d/$name" | Out-Null
  docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c "INSERT INTO public.schema_migrations(filename, sha256) VALUES ('$name', '$hash') ON CONFLICT (filename) DO NOTHING;" | Out-Null
}

# Представление и витрина последних миграций
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -v ON_ERROR_STOP=1 -c @"
CREATE OR REPLACE VIEW public.schema_migrations_recent AS
SELECT split_part(filename, '_', 1) AS version,
       filename,
       sha256 AS checksum,
       applied_at,
       (applied_at AT TIME ZONE 'Europe/Moscow') AS applied_msk
FROM public.schema_migrations
ORDER BY applied_at DESC;
"@

Info "`n=== Recent migrations ==="
docker compose exec -T db psql -U $PGUSER -d $PGDATABASE -c "SELECT * FROM public.schema_migrations_recent LIMIT 8;"
Info "`nAll migrations applied."
```

### `db/migrate.sh` (Linux/macOS, bash)

```bash
#!/usr/bin/env bash
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-15432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-dev_local_pw}"
PGDATABASE="${PGDATABASE:-wine_db}"
export PGPASSWORD

docker compose up -d db

echo "Waiting for Postgres readiness..."
for i in {1..60}; do
  if docker compose exec -T db pg_isready -U "$PGUSER" -d "$PGDATABASE" -h localhost -p 5432 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

psql_cmd=(docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -c)
"${psql_cmd[@]}" "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
"${psql_cmd[@]}" "CREATE EXTENSION IF NOT EXISTS vector;"
"${psql_cmd[@]}" "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
"${psql_cmd[@]}" "CREATE TABLE IF NOT EXISTS public.schema_migrations(filename text PRIMARY KEY, sha256 char(64), applied_at timestamptz NOT NULL DEFAULT now());"

for f in db/migrations/*.sql; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  sha=$(sha256sum "$f" | awk '{print tolower($1)}')
  exists=$(docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" -At -c "SELECT 1 FROM public.schema_migrations WHERE filename='${name}' LIMIT 1;")
  if [ "$exists" = "1" ]; then
    echo ">> SKIP $name (already applied)"; continue
  fi
  echo ">> Applying $name"
  docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -f "/docker-entrypoint-initdb.d/${name}"
  "${psql_cmd[@]}" "INSERT INTO public.schema_migrations(filename, sha256) VALUES ('${name}', '${sha}') ON CONFLICT (filename) DO NOTHING;"
done

"${psql_cmd[@]}" "CREATE OR REPLACE VIEW public.schema_migrations_recent AS
SELECT split_part(filename, '_', 1) AS version,
       filename,
       sha256 AS checksum,
       applied_at,
       (applied_at AT TIME ZONE 'Europe/Moscow') AS applied_msk
FROM public.schema_migrations
ORDER BY applied_at DESC;"

docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" -c "SELECT * FROM public.schema_migrations_recent LIMIT 8;"
echo "All migrations applied."
```

---

## Как поднимается БД в CI

В пайплайне перед тестами запускается `db`, затем применяются миграции:

```yaml
# .github/workflows/test.yml (фрагмент)
- name: Start DB
  run: docker compose up -d db

- name: Wait for DB readiness
  run: |
    for i in {1..60}; do
      if docker compose exec -T db pg_isready -U postgres -d wine_db -h localhost -p 5432 >/dev/null 2>&1; then
        exit 0
      fi
      sleep 2
    done
    echo "DB not ready"; exit 1

- name: Apply SQL migrations
  run: pwsh ./db/migrate.ps1
  shell: pwsh

- name: Run tests
  run: pytest -v --cov=api --cov=scripts --cov=etl --cov-report=xml --cov-report=term
```

**Плюс:** `/ready` в тестах проверяет наличие ключевых таблиц и индексов — это помогает ловить расхождения схемы.

---

## Миграции и схема

Миграции находятся в `db/migrations/` и включают:

- `0000_schema_migrations.sql` — регистрация применённых миграций.
- `0001_prices-and-search.sql` — `products`, `product_prices`, `inventory`, индексы (в т.ч. триграммы).
- `0002_price-history-guardrails.sql` — `btree_gist`, уникальные ограничения по периоду, guardrails.
- `0003_inventory-columns-and-asof.sql` — дополнительные поля остатков и индексы.
- `0004_diagnostics.sql`, `0005_price-check.sql` — диагностические и проверочные функции/представления.
- `0006_add-idempotency-tables.sql` — `envelopes`, `price_list_entries`.
- `0007_schema-migrations-view.sql` — удобная витрина `schema_migrations_recent`.

> Расширения: `pg_trgm`, `vector`, `pgcrypto` создаются автоматически.

---

## Тесты и покрытие

Локально:

```bash
pytest -v --cov=api --cov=scripts --cov=etl --cov-report=xml --cov-report=term
```

В CI — те же команды, БД и миграции запускаются автоматически. Покрытие сейчас ~**61%** (см. бейдж вверху).

---

## Траблшутинг

- **API контейнер «крутится» (restarting)** — проверь, что `api` запускается командой `python -m api.app` и каталог `api/` скопирован в образ (`Dockerfile`).
- **`/ready` показывает `products_search_idx: false`** — прогоните миграции: `pwsh ./db/migrate.ps1` или `bash ./db/migrate.sh`.
- **Ошибка `UndefinedTable` при `upsert_records()`** — отсутствуют таблицы/индексы: примените миграции.
- **Windows PowerShell не видит `jq`** — используйте `curl.exe ... | python -m json.tool` или `Invoke-WebRequest`.
- **Таймзона** — в Docker установлена `Europe/Moscow`; при необходимости поменяйте в `docker-compose.yml`.

---

## Лицензия

MIT
