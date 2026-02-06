# Wine Assistant 🍷

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Semgrep](https://github.com/glinozem/wine-assistant/actions/workflows/semgrep.yml/badge.svg)](../../actions/workflows/semgrep.yml)
[![Secrets](https://github.com/glinozem/wine-assistant/actions/workflows/secrets.yml/badge.svg)](../../actions/workflows/secrets.yml)

**Production-ready система управления винным каталогом** с REST API, ETL-пайплайном, справочником виноделен, автоматическим импортом изображений, историей остатков и расширенными возможностями экспорта данных.

Изначально учебный проект, Wine Assistant вырос в полноценное решение, демонстрирующее best practices современной backend-разработки на Python.

**Текущий статус:** Production-ready • 175+ тестов • M1 (Import Operations) Complete 🎉 • **Daily Import (Ops) Ready** 🎉 • Observability & Monitoring ready ✅ • AI Integration планируется (Sprint 8) 🔜

---

## 🎯 Ключевые возможности

### 📊 Управление данными и ETL

- **Daily Import (Ops)** — incremental imports без wipe volumes, Windows-friendly 🎉
- **Import Orchestrator** — production-grade система импорта с полным аудитом
- **Автоматический импорт прайс-листов** (Excel/CSV) с интеллектуальным парсингом
- **Идемпотентность импортов** по ключу `(supplier, as_of_date, file_sha256)`
- **Inventory tracking** — автоматические snapshot'ы с историей
- **Supplier normalization** — нормализация поставщиков
- **Extended price tracking** — list/final/current цены
- **Retry support** — автоматический retry failed импортов через orchestrator
- **Stale run detector** — автоматическая очистка зависших операций
- **Извлечение изображений из Excel** → автоматическое заполнение `image_url`
- **Справочник виноделен** (`wineries`) из PDF-каталога поставщика
- **Enrichment каталога** данными о регионе, производителе, сайтах виноделен
- **История цен и остатков** с автоматическим версионированием
- **Ежедневная синхронизация остатков** в `inventory_history` для аналитики и графиков
- **Карантин данных** для невалидных записей (Data Quality Gates)
- **Партиционирование** таблиц по кварталам для масштабирования

### 🔌 REST API & Интеграции

- **Публичный поиск** по каталогу с фильтрацией и сортировкой
- **SKU карточка** с полными данными о винодельне
- **История цен** и **история остатков** по временным диапазонам
- **Swagger/OpenAPI** документация из коробки
- **API-key авторизация** для защищённых endpoints
- **Structured JSON logging** с request tracking
- **Health checks** (liveness/readiness) для Kubernetes
- **Rate limiting** для защиты от перегрузки

### 📤 Экспорт и отчёты

- **Множественные форматы:** JSON, Excel (.xlsx), PDF
- **Экспорт результатов поиска** с фильтрами
- **PDF-карточки товаров** с изображениями
- **История цен в Excel** для аналитики
- **История остатков в Excel/JSON** с временной шкалой
- **Unicode поддержка** в PDF (кириллица, символ ₽)
- **Фиксированный набор полей** для каждого типа экспорта

### 📈 Визуализация и аналитика

- **Графики истории цен** (Chart.js) в веб-интерфейсе
- **Графики динамики остатков** по SKU
- **Временные срезы** с настраиваемыми диапазонами (`from`/`to`)
- **Экспорт данных для BI** (Excel/JSON)


### 🖥️ Витрина UI (`/ui`)

- Открыть: `http://localhost:18000/ui`
- UI использует **пагинацию** (`limit/offset`) и **бесконечную прокрутку**, поэтому загружает не только первые 30 позиций.
- По умолчанию включён фильтр **"Только в наличии"** (`in_stock=true`).
- Изображения SKU берутся из `image_url` (если задан) или через прокси-эндпоинт: `GET /sku/<code>/image`.

Если в UI отображается только 30 позиций — обычно это означает, что в контейнер попала старая версия `api/templates/ui.html`.
Пересоберите контейнер `api` и обновите страницу с очисткой кэша (Ctrl+F5).

### 🖼️ Работа с изображениями

- **Автоматическое извлечение** изображений из Excel-прайсов
- **Статическая раздача** через `/static/images/<SKU>.<ext>`
- **Каталог изображений**: по умолчанию `static/images` (можно переопределить `WINE_IMAGE_DIR`).
- **Кэш индекса изображений**: индекс строится один раз и автоматически обновляется при изменении каталога (mtime). Если каталог расположен на volume/сетевой FS и mtime «не шевелится», включите TTL через `WINE_IMAGE_INDEX_TTL_SECONDS` (0 = выключено; пример: `86400`).
- **Публичные URL** для каждого товара
- **Интеграция в экспорты** (XLSX с колонкой "Фото (URL)", PDF с изображением)

### 🏛️ Справочник виноделен

- **Централизованное хранение** данных о производителях
- **Импорт из PDF-каталога** с нормализацией названий
- **Обогащение продуктов** регионом и сайтом производителя
- **Русские названия** и **описания** виноделен для витрины
- **Автоматическая синхронизация** `products` ↔ `wineries`

### 📊 Observability & Monitoring

> **Production-grade мониторинг backup/DR операций** с Grafana dashboards

- **Grafana Dashboard** для мониторинга backup/restore/DR операций
  - 📈 Backups completed (last 24h) — количество завершённых бэкапов
  - ⏱️ Age since last backup — время с последнего бэкапа с цветовыми индикаторами
  - 🔄 Restore operations (last 7d) — количество операций восстановления
  - 🗑️ Remote pruned backups (last 7d) — статистика очистки старых бэкапов
- **Structured JSONL logging** для всех backup/DR операций
  - События: backup_local_started/completed, restore_local_started/completed, prune_*_completed, dr_smoke_started/completed/failed
  - Автоматический сбор метрик: file size, duration, deleted/kept counts
- **Promtail → Loki → Grafana pipeline** для централизованного сбора логов
- **Auto-refresh каждые 30 секунд** с настраиваемыми time ranges
- **Color-coded thresholds** для быстрого визуального контроля (green/yellow/red)

**Makefile команды для observability:**
```bash
make obs-up          # Запуск Grafana/Loki/Promtail
make obs-down        # Остановка observability stack
make obs-restart     # Перезапуск
make obs-logs        # Просмотр логов
```

**Dashboard доступен по адресу:** `http://localhost:15000/d/wine-assistant-backup-dr/backup-dr`

---

## 📥 Daily Import (Ops)

Daily Import — это операционный импорт Excel‑прайсов из `data/inbox/` с последующим перемещением обработанных файлов в `data/archive/` (или `data/quarantine/` при проблемах качества данных). Процесс идемпотентный: если файл уже был импортирован (тот же SHA‑256), он будет помечен как `SKIPPED` с причиной `ALREADY_IMPORTED_SAME_HASH`.

### Ключевые свойства

- **Два режима запуска**
  - **Auto** (`--mode auto`): берётся *самый новый* `.xlsx` из `data/inbox/`.
  - **Manual list** (`--mode files`): обрабатываются *ровно выбранные* файлы (имена должны совпадать с тем, что возвращает inbox/показывает UI).
- **После обработки файл уходит из inbox**
  - При `IMPORTED` и при `SKIPPED` файл обычно перемещается в `data/archive/...` (в результате `inbox` может стать пустым).
- **Результат всегда фиксируется как “run”** (run_id + список файлов + summary) и может быть запрошен по API.

---

### Способ 1: Web UI (рекомендуется для ручных запусков)

1. Откройте страницу: `http://localhost:18000/daily-import`
2. Введите `X-API-Key` (можно взять из `.env`: `API_KEY=...`)
3. Нажмите **«Обновить Inbox»**, выберите режим и запускайте импорт.

UI показывает:
- список файлов в inbox;
- итоговый статус run + детализацию по каждому файлу (IMPORTED / SKIPPED / ERROR / QUARANTINED);
- ссылки для скачивания архивного/карантинного файла (если доступно).

---

### Способ 2: Makefile

Поддерживаемые таргеты (см. `Makefile`):

```powershell
# показать inbox (внутри контейнера api)
make inbox-ls

# Auto: обработать самый новый файл
make daily-import

# Manual list: обработать выбранные файлы (ВАЖНО: имена без пробелов/кавычки могут быть неудобны для make)
make daily-import-files FILES="2025_12_24.xlsx 2025_12_25.xlsx"

# Windows-friendly: через PowerShell wrapper (поддерживает пробелы/кириллицу)
make daily-import-ps
make daily-import-files-ps FILES="2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"

# история последних run’ов и просмотр конкретного
make daily-import-history
make daily-import-show RUN_ID=<uuid>

# housekeeping
make daily-import-cleanup-archive DAYS=90
make daily-import-quarantine-stats
```

---

### Способ 3: PowerShell wrapper (Windows-friendly)

Скрипт: `scripts\run_daily_import.ps1` — удобен на Windows, т.к. проще управлять quoting (пробелы/кириллица).

```powershell
# Auto
.\scripts\run_daily_import.ps1 -Mode auto

# Manual list: можно массивом
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс_Легенда_Виноделия.xlsx","2025_12_25 Другой прайс.xlsx"

# Manual list: можно одной строкой CSV
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс_Легенда_Виноделия.xlsx,2025_12_25 Другой прайс.xlsx"
```

Скрипт возвращает ненулевой exit code при `FAILED/TIMEOUT` и при наличии `QUARANTINED` файлов (это удобно для CI/smoke).

---

### Дополнительно: прямой запуск внутри контейнера (debug)

```powershell
# Auto
docker-compose exec -T api python -m scripts.daily_import_ops --mode auto

# Manual list (имена файлов должны совпадать с inbox)
docker-compose exec -T api python -m scripts.daily_import_ops --mode files --files "2025_12_24 Прайс.xlsx" "2025_12_25 Другой прайс.xlsx"
```

---

### Проверка результата по API (PowerShell)

```powershell
$k = (Get-Content .\.env | Where-Object { $_ -match '^API_KEY=' } | Select-Object -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()

# список inbox (требует X-API-Key)
irm "http://localhost:18000/api/v1/ops/daily-import/inbox" -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 5

# детали конкретного run (run_id берите из вывода/логов/UI)
$rid = "<run_id>"
irm "http://localhost:18000/api/v1/ops/daily-import/runs/$rid" -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 10
```

См. также: **[docs/dev/run-sync-powershell.md](docs/dev/run-sync-powershell.md)** — как дергать `POST /api/v1/ops/daily-import/run-sync` из PowerShell (PS 5.1 vs 7+) и почему `curl.exe --data-raw` часто ломает JSON.

Примечание: используйте `docker compose ...` вместо `docker-compose ...`, если в вашей среде нет алиаса `docker-compose` (в проекте есть заметки по этой теме в документации).

## 🧑‍💻 Developer Docs (для разработчиков)

Этот блок — краткий “how-to” для локальной разработки и поддержки проекта: поднять окружение, быстро проверить изменения, запустить импорт/ops-процессы и провести базовую диагностику.

### 1) Предварительные требования

- **Docker + Docker Compose v2** (команда `docker compose`).
- **Python 3.11+** (если запускаете что-то вне контейнеров).
- (Опционально) **Make** — удобно, но не обязательно (на Windows можно через PowerShell).

---

### 2) Быстрый dev-цикл (Docker-first)

1. Поднимите сервисы (как минимум `db` и `api`):
   ```bash
   docker compose up -d --build
   ```

2. Проверьте, что API “живой”:
   ```bash
   curl http://localhost:18000/health
   ```

3. Откройте:
   - UI: `http://localhost:18000/ui`
   - Swagger/OpenAPI: `http://localhost:18000/docs`

4. Просмотр логов:
   ```bash
   docker compose logs -f api
   docker compose logs -f db
   ```

Если вы используете Makefile, то для повседневной разработки ориентируйтесь на цели в разделе “Makefile команды” ниже.

---

### 3) Переменные окружения и доступ к защищённым endpoints

- Основные значения лежат в `.env` (локально создаётся из `.env.example`).
- Для защищённых ops/API endpoints используйте заголовок:
  - `X-API-Key: <API_KEY из .env>`
- Для изображений SKU (эндпоинт `GET /sku/<code>/image`):
  - `WINE_IMAGE_DIR`: каталог изображений (по умолчанию `static/images`).
  - `WINE_IMAGE_INDEX_TTL_SECONDS`: TTL (секунды) для пересборки индекса изображений (0 = выключено; включайте если mtime каталога не обновляется на volume/сетевой FS).

Проверка через PowerShell:
```powershell
$k = (Get-Content .\.env | Where-Object { $_ -match '^API_KEY=' } | Select-Object -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()
irm "http://localhost:18000/health" -Headers @{ "X-API-Key" = $k }
```

---

### 4) Тесты и базовые проверки качества

1. Запуск тестов:
   ```bash
   pytest
   ```

2. Тесты с coverage:
   ```bash
   pytest --cov=api --cov=scripts --cov-report=html
   ```

Если у вас есть DB‑зависимые unit/integration тесты — поднимите `db` и запускайте тесты после прогрева.

---

### 5) E2E smoke (проверка “всё работает вместе”)

Полный сквозной сценарий проверок обычно оформлен как Make‑цель (если в проекте есть):
```bash
make smoke-e2e
```

---

### 6) Daily Import / Ops Daily Import (inbox → archive/quarantine)

> Примечание: в некоторых ветках/релизах импорт описан как **Daily Import v1.0.4**, в более новых — как **Ops Daily Import**. Логика одинакова: берём `.xlsx` из `data/inbox/`, импортируем, затем переносим файл в `data/archive/` или `data/quarantine/`.

#### Предварительные условия

1. Поднимите сервисы:
   ```bash
   docker compose up -d --build db api
   ```
2. Положите `.xlsx` в `./data/inbox/` на хосте (volume в контейнер: `/app/data/inbox/`).
3. Возьмите `API_KEY` из `.env` и используйте как `X-API-Key` (для UI / API).

#### Способ 1 — Web UI (удобно для ручных запусков)

- Для веток с Daily Import v1.x обычно: `http://localhost:18000/daily-import` (или страница из раздела UI документации).
- Для веток с Ops Daily Import: отдельная UI‑форма “Daily Import”.

Общий сценарий:
1. Откройте страницу импорта.
2. Вставьте `X-API-Key`.
3. Обновите список inbox и запустите импорт (auto/manual).

Ожидаемое поведение: при **успешной обработке** файл исчезает из inbox и появляется в `data/archive/...`.

#### Способ 2 — PowerShell wrapper (Windows-friendly)

Auto (самый новый файл):
```powershell
.\scripts\run_daily_import.ps1 -Mode auto
```

Manual (список файлов; пробелы/кириллица поддерживаются; можно одной строкой CSV):
```powershell
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс.xlsx, 2025_12_25 Другой прайс.xlsx"
```

#### Способ 3 — Makefile

Auto:
```bash
make daily-import
```

Windows-friendly (в разных версиях цели могут называться по‑разному):
```bash
make daily-import-ps1        # встречается в Daily Import v1.0.4
make daily-import-ps         # встречается в Ops Daily Import
```

Manual list:
```bash
make daily-import-files FILES="file1.xlsx file2.xlsx"
make daily-import-files-ps1 FILES="file1.xlsx,file2.xlsx"   # вариант для ps1-обёртки
make daily-import-files-ps  FILES="file1.xlsx,file2.xlsx"   # вариант для ops-обёртки
```

---

### 7) `docker compose` vs `docker-compose`

В проекте рекомендуется **Compose v2** (`docker compose`). Если в вашей среде доступен только `docker-compose`, используйте его эквивалентно.

---

## 🔧 Fresh Deployment & Bootstrap

### Bootstrap from Scratch

Для initial setup или полного rebuild:

```powershell
# Full bootstrap (Windows)
.\scripts\bootstrap_from_scratch.ps1 -RebuildImages

# What it does:
# 1. docker compose down -v (wipe volumes)
# 2. docker compose build
# 3. docker compose up -d
# 4. Wait for API readiness
# 5. Import all price lists from inbox (sorted by date)
# 6. Load wineries catalog
# 7. Enrich products (region/site)
# 8. Backfill missing data
# 9. Create inventory snapshot
# 10. Run verification checks
```

**Expected duration:** 2-5 minutes (зависит от размера данных)

### E2E Smoke Test

Комплексная end-to-end валидация:

```bash
# Full test with fresh deployment
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1 SMOKE_BUILD=1

# Test without rebuild
make smoke-e2e SMOKE_SUPPLIER=dreemwine

# With all options
make smoke-e2e \
  SMOKE_SUPPLIER=dreemwine \
  SMOKE_FRESH=1 \
  SMOKE_BUILD=1 \
  SMOKE_STALE_MODE=run \
  SMOKE_API_SMOKE=1
```

**Что валидируется:**
- ✅ Container startup and readiness
- ✅ Daily import workflow
- ✅ Stale detector (optional)
- ✅ SQL data integrity checks
- ✅ API smoke tests (optional)

---

## 📥 Import Operations (M1 Complete) 🎉

> **Production-ready импорт** с идемпотентностью, аудитом и автоматизацией

Импорт выполняется через **Import Orchestrator** с записью статусов и метрик в таблицу `import_runs`.
Для интеграции с legacy ETL используется адаптер `scripts/import_targets/run_daily_adapter.py`.

**Ключевые компоненты:**
- **Import Orchestrator** — единая точка входа для всех импортов
- **Import Run Registry** — журнал попыток с метриками (`import_runs` table)
- **Stale Run Detector** — автоматическая очистка зависших импортов
- **Legacy ETL Adapter** — интеграция с существующим `etl/run_daily`
- **Ingest Envelope** — трассировка файлов через `file_sha256`

**Быстрый старт (ежедневный импорт):**
```powershell
# Wrapper скрипт автоматически:
# - найдёт последний файл по дате в имени (2025_12_24 Прайс...)
# - извлечёт as_of_date из имени файла
# - запустит orchestrator

.\scripts\run_daily_import.ps1 -Supplier "dreemwine"

# Expected output:
# INFO import_run_success metrics={'total_rows_processed': 262, 'rows_skipped': 298}
```

**Ручной запуск (точечная диагностика):**
```powershell
python -m scripts.run_import_orchestrator `
  --supplier "dreemwine" `
  --file "data/inbox/2025_12_10 Прайс_Легенда_Виноделия.xlsx" `
  --as-of-date "2025-12-10" `
  --import-fn "scripts.import_targets.run_daily_adapter:import_with_run_daily"
```

**Проверка в БД:**
```powershell
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, status, total_rows_processed, rows_skipped, envelope_id, created_at
FROM import_runs
ORDER BY created_at DESC LIMIT 10;"
```

**Автоматизация (Windows Task Scheduler):**
```powershell
# Ежедневный импорт (09:00)
$taskName = "wine-assistant daily import"
$scriptPath = (Resolve-Path ".\scripts\run_daily_import.ps1").Path
schtasks /Create /TN $taskName /SC DAILY /ST 09:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Supplier dreemwine" /F

# Stale detector (каждые 15 минут)
$taskName = "wine-assistant stale detector"
$scriptPath = (Resolve-Path ".\scripts\run_stale_detector.ps1").Path
schtasks /Create /TN $taskName /SC MINUTE /MO 15 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" /F
```

**Особенности:**
- ✅ **Идемпотентность:** ключ `(supplier, as_of_date, file_sha256)` — повторный импорт → skip
- ✅ **Retry support:** failed импорт можно перезапустить той же командой
- ✅ **Full audit:** каждая попытка (success/failed/skipped) в `import_runs`
- ✅ **File traceability:** связь с файлом через `envelope_id`
- ✅ **Automatic cleanup:** stale detector переводит зависшие runs в `rolled_back`
- ✅ **Production validated:** DreemWine case (262 rows in 1.5s)

**Документация:**
- **Архитектура:** [`docs/dev/import_flow.md`](docs/dev/import_flow.md) — компоненты, статусы, контракты
- **Runbook:** [docs/ops_daily_import.md](docs/ops_daily_import.md) — contracts, statuses, troubleshooting
- **Quick Reference:** [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md#import-operations) — command cheat sheet

**Мониторинг:**
```sql
-- Staleness check (критический порог: 24h)
SELECT supplier, hours_since_success, last_success_at
FROM v_import_staleness WHERE hours_since_success > 24;

-- Failed imports (last 7d)
SELECT supplier, as_of_date, error_summary, created_at
FROM import_runs
WHERE status = 'failed' AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

---

## 🤖 AI Capabilities (В разработке - Sprint 8)

> ⚠️ **ВНИМАНИЕ:** AI-слой ещё не реализован. Ниже представлен дизайн и план работ Sprint 8.
>
> Текущий статус: Issues #128-134 открыты, инфраструктура в проектировании.

**Планируемые возможности:**

- **OpenAI/VseLLM интеграция** для LLM-функций (Issue #128)
- **Векторные embeddings** для семантического поиска (Issue #129)
- **Semantic Search** по описаниям вин (Issue #130)
- **AI Wine Description Generator** - автогенерация описаний (Issue #131)
- **AI Testing Infrastructure** (Issue #132)
- **AI Wine Sommelier** с памятью разговора (LangGraph) (Issue #134)
- **AI Monitoring Dashboard** для отслеживания расходов (Issue #133)
- **Cascade Model Architecture** (nano → mini → sonnet-4) для оптимизации затрат

---

## 🛠️ Инфраструктура

- **Docker Compose** окружение с PostgreSQL 16 + pgvector
- **Автоматические миграции** БД с версионированием
- **CI/CD Pipeline** с GitHub Actions
- **Pre-commit hooks** для проверки кода
- **Ruff** для линтинга и форматирования
- **Pytest** с >80% coverage
- **Structured logging** с JSON формированием
- **Grafana + Loki + Promtail** для observability
- **MinIO** для backup storage

---

## 🚀 Quick Start

### Вариант A: Docker (рекомендуется)

```bash
# 1. Клонирование репозитория
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# 2. Настройка окружения
cp .env.example .env
# Отредактируйте .env: установите API_KEY и другие параметры

# 3. Запуск (без observability)
docker compose up -d

# 4. Запуск с observability (Grafana/Loki/Promtail)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# 5. Проверка
curl http://localhost:18000/health

# 6. Открыть UI
# http://localhost:18000/ui

# 7. Открыть Swagger
# http://localhost:18000/docs
```

### Вариант B: Локальная разработка

```bash
# 1. Клонирование
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# 2. Виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\Activate     # Windows

# 3. Установка зависимостей
pip install -r requirements.txt

# 4. Настройка .env
cp .env.example .env

# 5. Запуск PostgreSQL
docker compose up -d db

# 6.️ Миграции БД (bootstrap + schema evolution)

После первого запуска контейнеров необходимо применить bootstrap-скрипт и канонические миграции БД.

## Docker / Linux / macOS

```bash
# Применить bootstrap (db/init.sql при необходимости) + миграции (db/migrations)
make db-migrate
```

## Windows (PowerShell)

```powershell
# Применить bootstrap (db/init.sql при необходимости) + миграции (db/migrations)
.\db\migrate.ps1
```

## Проверка

```bash
# Открыть psql в контейнере
make db-shell
```

В psql:

```sql
-- Должны быть применённые миграции
select * from public.schema_migrations order by version;

-- Базовая проверка guardrails по product_prices
select count(*) as invalid_ranges
from public.product_prices
where effective_to is not null and effective_to <= effective_from;
```

## Политика и troubleshooting

- Источник истины по изменениям схемы: `db/migrations/NNNN_*.sql`.
- `db/init.sql` используется только как bootstrap для базовых таблиц (`products`, `inventory`) и не должен содержать «инкрементальные» изменения (индексы/функции/новые таблицы).
- Если CI сообщает, что изменены старые миграции — откатите правку и добавьте новую миграцию.

Подробнее:
- `docs/dev/db-migrations.md` — канон миграций и CI-guardrails.
- `docs/dev/effective_ranges_remediation.md` — playbook исправления effective ranges в `product_prices`.


# 7. Запуск API
flask run --host=0.0.0.0 --port=18000

# 8. Запуск тестов
pytest
```

### Первый импорт данных

```bash
# Bootstrap from scratch (recommended for first setup)
.\scripts\bootstrap_from_scratch.ps1 -RebuildImages

# Or manual daily import
make daily-import
```

### Проверка Backup/DR и Observability

```powershell
# Создать тестовый бэкап
make backup-local

# Запустить DR smoke test
make dr-smoke-truncate DR_BACKUP_KEEP=2

# С автоматическим управлением Promtail (рекомендуется для Windows)
make dr-smoke-truncate DR_BACKUP_KEEP=2 MANAGE_PROMTAIL=1

# Посмотреть логи в Grafana
# Открыть: http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
```

---

## 📊 Архитектура системы

```
┌──────────────────────────────────────────────┐
│         Presentation Layer                   │
│  • REST API (Flask)                          │
│  • Swagger Documentation                     │
│  • Web UI (/ui)                              │
└─────────────────┬────────────────────────────┘
                  │
┌─────────────────┴────────────────────────────┐
│         Business Logic Layer                 │
│  • Product Search & Filtering                │
│  • Price History Tracking                    │
│  • Inventory Management                      │
│  • Export Services (JSON/XLSX/PDF)           │
│  • Winery Management                         │
│  • Daily Import (Ops) 🎉                    │
│  • Import Orchestrator (M1) 🎉               │
└─────────────────┬────────────────────────────┘
                  │
┌─────────────────┴────────────────────────────┐
│         Data Layer                           │
│  • PostgreSQL 16 + pgvector                  │
│  • Partitioned Tables (Quarterly)            │
│  • Automated Migrations                      │
│  • Data Quality Gates                        │
│  • Import Run Registry (import_runs)         │
│  • Inventory History (inventory_history)     │
└──────────────────────────────────────────────┘

         Observability Stack
┌──────────────────────────────────────────────┐
│  Promtail → Loki → Grafana                   │
│  • Structured JSONL Logging                  │
│  • Backup/DR Metrics                         │
│  • Import Operations Monitoring              │
│  • API Request Tracking                      │
│  • Real-time Dashboards                      │
└──────────────────────────────────────────────┘

         Storage & Backup
┌──────────────────────────────────────────────┐
│  MinIO (S3-compatible)                       │
│  • Backup Storage                            │
│  • Automated Pruning                         │
│  • DR Recovery Testing                       │
└──────────────────────────────────────────────┘
```

---

## 📚 Документация

- **[INDEX.md](INDEX.md)** — Навигация по документации
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** — Шпаргалка по командам
- **[CHANGELOG.md](CHANGELOG.md)** — История изменений
- **[docs/changes_daily_import.md](docs/changes_daily_import.md)** — Daily Import (Ops) guide
- **[docs/MIGRATION_GUIDE_v1.0.4.md](docs/MIGRATION_GUIDE_v1.0.4.md)** — Migration guide
- **[docs/dev/import_flow.md](docs/dev/import_flow.md)** — Import Operations архитектура
- **[docs/architecture.md](docs/architecture.md)** — Общая архитектурная диаграмма
- **[docs/ops_daily_import.md](docs/ops_daily_import.md)** — Ops Daily Import runbook
- **[docs/dev/backup-dr-runbook.md](docs/dev/backup-dr-runbook.md)** — Backup/DR руководство
- **[docs/dev/web-ui.md](docs/dev/web-ui.md)** — Документация UI
- **[docs/dev/windows-powershell-http.md](docs/dev/windows-powershell-http.md)** — PowerShell для API
- **[docs/dev/run-sync-powershell.md](docs/dev/run-sync-powershell.md)** — Как дергать `/run-sync` из PowerShell (5.1 vs 7+)

---

## 🔧 Makefile команды

### Daily Import (Ops)
```bash
make inbox-ls
make daily-import

# manual list (простые имена)
make daily-import-files FILES="file1.xlsx file2.xlsx"

# Windows-friendly (пробелы/кириллица) — через PowerShell wrapper
make daily-import-ps
make daily-import-files-ps FILES="2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"

# история и просмотр run по id
make daily-import-history
make daily-import-show RUN_ID=<uuid>
```

```

### Development
```bash
make dev-up          # Запуск dev окружения
make dev-down        # Остановка
make dev-logs        # Просмотр логов
```

### Observability
```bash
make obs-up          # Запуск Grafana/Loki/Promtail
make obs-down        # Остановка observability stack
make obs-restart     # Перезапуск
make obs-logs        # Логи observability сервисов
```

### Backup & DR
```bash
make backup-local           # Создать локальный бэкап
make backup                 # Бэкап + upload в MinIO + prune
make restore-local          # Восстановить из локального бэкапа
make restore-remote-latest  # Восстановить из MinIO (latest)
make dr-smoke-truncate      # DR тест (truncate mode)
make dr-smoke-dropvolume    # DR тест (dropvolume mode)
```

### Testing & Bootstrap
```bash
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1  # E2E smoke test
```

### Storage (MinIO)
```bash
make storage-up             # Запуск MinIO
make storage-down           # Остановка MinIO
make backups-list-remote    # Список бэкапов в MinIO
```

---

## 🧪 Тестирование

```bash
# Запуск всех тестов
pytest

# С coverage
pytest --cov=api --cov=scripts --cov-report=html

# Только unit тесты
pytest tests/unit/

# Только integration тесты
pytest tests/integration/

# С подробным выводом
pytest -v

# Import Operations tests (requires DB) - PowerShell
$env:RUN_DB_TESTS="1"; pytest tests/unit/test_import_run_registry.py
$env:RUN_DB_TESTS="1"; pytest tests/unit/test_import_orchestrator_flow.py

# Daily import smoke test
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1
```

**Test Coverage:** 175+ тестов, >80% покрытие

---

## 🔐 Безопасность

- ✅ API Key авторизация
- ✅ Pre-commit hooks с gitleaks
- ✅ Semgrep сканирование в CI
- ✅ Secrets detection в GitHub Actions
- ✅ Rate limiting на API endpoints
- ✅ Input validation на всех endpoints
- ✅ SQL injection защита (parameterized queries)

---

## 📈 Мониторинг и алертинг

### Grafana Dashboards

1. **Wine Assistant — Backup & DR**
   - URL: `http://localhost:15000/d/wine-assistant-backup-dr/backup-dr`
   - Панели: Backups, Age since last backup, Restores, Pruned backups
   - Auto-refresh: 30s

2. **Wine Assistant — API** (опционально)
   - URL: `http://localhost:15000/d/wine-assistant-api`
   - Панели: Request rate, Response times, Error rate
   - Auto-refresh: 10s

### Loki Query Examples

```logql
# Все backup события за последние 24 часа
{job="wine-backups", event="backup_local_completed"} [24h]

# Ошибки DR smoke tests
{job="wine-backups", event="dr_smoke_failed"}

# Все события с deleted_count > 0
{job="wine-backups"} | json | deleted_count > 0
```

---

## 🤝 Contributing

1. Fork репозитория
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменений (`git commit -m 'feat: add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

**Требования:**
- Все тесты должны проходить (`pytest`)
- Ruff checks должны проходить (`ruff check .`)
- Pre-commit hooks должны быть установлены (`pre-commit install`)

---

## 📜 Лицензия

Этот проект создан в образовательных целях.

---

## 🙏 Благодарности

- Flask для веб-фреймворка
- PostgreSQL за надёжную БД
- Docker за контейнеризацию
- Grafana + Loki + Promtail за observability
- MinIO за S3-совместимое хранилище
- Chart.js за графики в UI

---

**Made with ❤️ and 🍷**



## Developer docs: Ops Daily Import (inbox → archive/quarantine)

Ниже — практические способы запустить **Ops Daily Import** (обработка Excel-прайсов из `data/inbox/` с перемещением в `data/archive/` или `data/quarantine/`).

### Предварительные условия

1. Поднимите сервисы:
   - `docker compose up -d --build db api`
2. Положите `.xlsx` в `./data/inbox/` на хосте (это volume в контейнер: `/app/data/inbox/`).
3. (Для UI / API) Возьмите `API_KEY` из `.env` и используйте как `X-API-Key`.

### Способ 1 — Web UI (Windows-friendly)

1. Откройте страницу: `http://localhost:18000/daily-import`
2. Вставьте `X-API-Key` (можно сохранить в `localStorage`).
3. Нажмите **Обновить Inbox**, затем выберите:
   - **Auto** — обработать самый новый файл в inbox
   - **Manual** — отметить конкретные файлы галочками
4. Нажмите **Запустить импорт** и дождитесь результата.

Ожидаемое поведение: при **успешной обработке** файл исчезает из inbox и появляется в `data/archive/...`.

### Способ 2 — PowerShell wrapper (через контейнер)

Auto (самый новый файл):

```powershell
.\scripts\run_daily_import.ps1 -Mode auto
```

Manual (список файлов; поддерживаются пробелы и кириллица; можно через запятую):

```powershell
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс_Легенда_Виноделия.xlsx"
```

Несколько файлов:

```powershell
.\scripts\run_daily_import.ps1 -Mode files -Files "file 1.xlsx,file 2.xlsx"
```

Скрипт печатает JSON результата и выставляет exit code:
- `0` — OK / OK_WITH_SKIPS без карантина
- `1` — есть QUARANTINED
- `2` — FAILED / TIMEOUT
- `4` — inbox пуст (NO_FILES_IN_INBOX)
- `5` — не удалось распарсить JSON

### Способ 3 — Makefile (кросс-платформенно)

Auto:

```powershell
make daily-import
```

Manual (внимание: Makefile-таргет **не дружит** с именами файлов, содержащими пробелы; для Windows предпочтительнее wrapper ниже):

```powershell
make daily-import-files FILES="file1.xlsx file2.xlsx"
```

Windows-friendly (через wrapper):

```powershell
make daily-import-ps
make daily-import-files-ps FILES="2025_12_24 Прайс_Легенда_Виноделия.xlsx"
```

Дополнительно:

```powershell
make inbox-ls
make daily-import-history
make daily-import-show RUN_ID=<uuid>
make daily-import-quarantine-stats
```

### Примечание про `docker compose` vs `docker-compose`

В документации и Makefile допускаются оба варианта. В проекте рекомендуется `docker compose` (Compose V2). Если у вас установлен только `docker-compose`, задайте переменную:

```powershell
$env:DOCKER_COMPOSE="docker-compose"
make dev-up
```
