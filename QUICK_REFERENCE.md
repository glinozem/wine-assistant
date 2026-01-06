# Wine Assistant - Краткая шпаргалка

## 🔑 Базовая настройка PowerShell

```powershell
# Установка API ключа
$env:API_KEY = "ВАШ_API_КЛЮЧ"

# Базовые переменные
$baseUrl = "http://localhost:18000"
$headers = @{ "X-API-Key" = $env:API_KEY }

# Проверка
echo $env:API_KEY
```

---

## 📥 Daily Import (Ops)

### 1) Web UI

```text
http://localhost:18000/daily-import
```

### 2) Makefile

```powershell
make inbox-ls
make daily-import

# manual list (простые имена)
make daily-import-files FILES="file1.xlsx file2.xlsx"

# Windows-friendly (пробелы/кириллица) — через PowerShell wrapper
make daily-import-files-ps FILES="2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"

make daily-import-history
make daily-import-show RUN_ID=<uuid>
```

### 3) PowerShell wrapper (Windows)

```powershell
.\scripts\run_daily_import.ps1 -Mode auto
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"
```

### 4) Direct docker-compose exec (debug)

```powershell
docker-compose exec -T api python -m scripts.daily_import_ops --mode auto
docker-compose exec -T api python -m scripts.daily_import_ops --mode files --files "file1.xlsx" "file2.xlsx"
```
## 📊 Import Operations (M1 Complete) 🎉

### Legacy Import Orchestrator (Advanced)

**Note:** For regular daily operations, use `make daily-import` above. The orchestrator is for advanced scenarios.

```powershell
python -m scripts.run_import_orchestrator `
  --supplier "dreemwine" `
  --file "data/inbox/2025_12_10 Прайс_Легенда_Виноделия.xlsx" `
  --as-of-date "2025-12-10" `
  --import-fn "scripts.import_targets.run_daily_adapter:import_with_run_daily"

# Expected output:
# INFO import_run_success metrics={'total_rows_processed': 262, 'rows_skipped': 298}
```

### Monitoring

```powershell
# Staleness check
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT supplier, hours_since_success, last_success_at,
       failed_count_7d, currently_running, has_success
FROM v_import_staleness
ORDER BY supplier;"

# Failed imports (last 7d)
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT supplier, as_of_date, error_summary, created_at
FROM import_runs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;"

# Currently running
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, started_at,
       EXTRACT(EPOCH FROM (NOW() - started_at))/60 as minutes_running
FROM import_runs
WHERE status='running'
ORDER BY minutes_running DESC;"

# Success rate (last 7d)
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT supplier,
       COUNT(*) FILTER (WHERE status = 'success') as success_count,
       COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
       ROUND(
         100.0 * COUNT(*) FILTER (WHERE status = 'success') /
         NULLIF(COUNT(*) FILTER (WHERE status IN ('success', 'failed')), 0),
         2
       ) as success_rate_pct
FROM import_runs
WHERE created_at > NOW() - INTERVAL '7 days'
  AND status IN ('success', 'failed')
GROUP BY supplier;"
```

### Stale Detector (зависшие импорты)

```powershell
# Dry-run: проверить параметры и команду без запуска
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose -WhatIf

# Реальный запуск с диагностикой
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose

# Тихий запуск (без диагностики)
.\scripts\run_stale_detector.ps1
```

---

## 📊 Observability & Monitoring

### Запуск observability stack

```powershell
# Запуск Grafana + Loki + Promtail
make obs-up

# Альтернатива через docker compose
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# Остановка
make obs-down

# Перезапуск
make obs-restart

# Логи observability сервисов
make obs-logs
```

### Grafana Dashboard

```powershell
# Открыть Grafana в браузере:
# http://localhost:15000
# Login: admin / Password: admin

# Backup/DR Dashboard:
# http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
```

---

## 💾 Backup & DR операции

### Создание бэкапов

```powershell
# Локальный бэкап
make backup-local

# Полный цикл: backup + upload to MinIO + prune
make backup BACKUP_KEEP=10

# Проверка бэкапов
ls backups/
```

### Восстановление

```powershell
# Восстановить из локального бэкапа (latest)
make restore-local

# Восстановить из конкретного файла
make restore-local FILE=backups/wine_db_20251222_140049.dump

# Восстановить из MinIO (latest remote)
make restore-remote-latest
```

### DR Smoke Tests

```powershell
# DR test (truncate mode) - быстрый
make dr-smoke-truncate DR_BACKUP_KEEP=2

# С автоматическим управлением Promtail (рекомендуется для Windows)
make dr-smoke-truncate DR_BACKUP_KEEP=2 MANAGE_PROMTAIL=1
```

---

## 🧪 Smoke Check

```powershell
# Быстрый smoke check
.\scripts\quick_smoke_check.ps1

# Полный smoke check
.\scripts\manual_smoke_check.ps1

# E2E smoke test
make smoke-e2e SMOKE_SUPPLIER=dreemwine
```

---

## 🐳 Docker команды

### Управление контейнерами

```powershell
# Запуск
docker compose up -d

# Запуск с observability
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# Остановка
docker compose down

# Логи
docker compose logs api -f

# Статус
docker compose ps
```

---

## 📝 Быстрые проверки

### Health Check

```powershell
# Liveness
Invoke-RestMethod "$baseUrl/live"

# Readiness
Invoke-RestMethod "$baseUrl/ready"

# Health
Invoke-RestMethod "$baseUrl/health"
```

### Поиск товаров

```powershell
# Простой поиск
Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=5" -Headers $headers

# С фильтрами
Invoke-RestMethod "$baseUrl/api/v1/products/search?color=red&in_stock=true&limit=10" -Headers $headers
```

### Карточка SKU

```powershell
# Полная карточка
$code = "D010210"
Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers | ConvertTo-Json -Depth 10

# Inventory history
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/inventory-history" -Headers $headers | ConvertTo-Json -Depth 5

# Price history
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/price-history" -Headers $headers | ConvertTo-Json -Depth 5
```

---

## 🛠️ Troubleshooting

### Проблема: API ключ не работает

```powershell
# Проверить переменную
echo $env:API_KEY

# Переустановить
$env:API_KEY = "новый_ключ"

# Проверить в .env файле
cat .env | Select-String "API_KEY"
```

### Проблема: Контейнер не стартует

```powershell
# Посмотреть логи
docker compose logs api --tail=50

# Проверить статус
docker compose ps

# Пересоздать контейнер
docker compose up -d --force-recreate api
```

### Проблема: Daily import fails

1) Убедитесь, что сервисы запущены:

```powershell
docker-compose up -d --build db api
```

2) Проверьте, что в `data/inbox/` реально есть `.xlsx` файлы:

```powershell
Get-ChildItem .\data\inbox
docker-compose exec api ls -la /app/data/inbox
```

3) Запустите импорт в debug‑режиме (внутри контейнера):

```powershell
docker-compose exec -T api python -m scripts.daily_import_ops --mode auto
```

4) Если запуск был через UI/PS/Make — возьмите `run_id` из ответа и запросите детали по API:

```powershell
$k = (Get-Content .\.env | Where-Object { $_ -match '^API_KEY=' } | Select-Object -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()
$rid = "<run_id>"

irm "http://localhost:18000/api/v1/ops/daily-import/runs/$rid" -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 10
```

5) Частые причины:
- **NO_FILES_IN_INBOX** — inbox пуст.
- **File not found** в manual list — выбран файл, который уже был перемещён в archive прошлым запуском; обновите inbox и выберите актуальные имена.
- **403** — неверный/пустой `X-API-Key`.
## 📚 Полезные ссылки

- **API Swagger:** http://localhost:18000/docs
- **Adminer:** http://localhost:18080
- **Grafana:** http://localhost:15000 (admin/admin)
- **Backup/DR Dashboard:** http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
- **GitHub:** https://github.com/glinozem/wine-assistant
- **Documentation:** docs/changes_daily_import.md
- **Changelog:** CHANGELOG.md

---

**Создано:** 04 декабря 2025
**Обновлено:** 31 декабря 2025 (Ops Daily Import)
**Версия:** 2.0
**Для:** Wine Assistant v0.4.0+ (M1 Complete + Ops Daily Import)

## Daily Import (Ops) — current

### 0) Поднять сервисы

```bash
docker compose up -d --build db api
```

### 1) Положить файл в inbox

Скопируйте `.xlsx` в `./data/inbox/` на хосте (в контейнере это `/app/data/inbox/`).

### 2) Запуск (3 способа)

**A. Web UI**

- `http://localhost:18000/daily-import`
- `X-API-Key` берётся из `.env` (header `X-API-Key`).

**B. PowerShell wrapper (Windows-friendly)**

```powershell
.\scripts\run_daily_import.ps1 -Mode auto
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс_Легенда_Виноделия.xlsx"
```

**C. Makefile**

```bash
make daily-import
make daily-import-ps
```

Manual list:

```bash
make daily-import-files FILES="file1.xlsx file2.xlsx"
make daily-import-files-ps FILES="2025_12_24 Прайс_Легенда_Виноделия.xlsx"
```

### 3) Ожидаемый результат

- Успех: файл перемещается в `data/archive/<YYYY-MM>/...`
- Проблемы по качеству/валидации: файл перемещается в `data/quarantine/...` (если включено в пайплайне)
- Если всё уже импортировано: статус `OK_WITH_SKIPS`, причина `ALREADY_IMPORTED_SAME_HASH`

### Legacy заметка

Если в старых документах/issue встречается `scripts.daily_import` или `scripts/daily_import.py`, это **устаревшие** названия.
Текущий оркестратор: `scripts/daily_import_ops.py` и запуск как:

```powershell
docker-compose exec -T api python -m scripts.daily_import_ops --mode auto
```
