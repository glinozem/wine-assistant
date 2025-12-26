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

## 📥 Import Operations (M1 Complete) 🎉

### Ежедневный импорт (рекомендуется)

Wrapper скрипт автоматически:
- Найдёт последний файл по дате в имени (`2025_12_24 Прайс...xlsx`)
- Извлечёт `as_of_date` из имени файла
- Запустит orchestrator

```powershell
# Простейший вариант
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"

# С диагностикой (показывает топ-5 кандидатов + выбранный файл)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose

# Dry-run (не запускает импорт, только показывает что будет сделано)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose -WhatIf

# С явным указанием файла
.\scripts\run_daily_import.ps1 `
  -Supplier "dreemwine" `
  -FilePath "data/inbox/2025_12_10 Прайс_Легенда_Виноделия.xlsx"

# Override as_of_date (если бизнес-дата ≠ дата в имени)
.\scripts\run_daily_import.ps1 `
  -Supplier "dreemwine" `
  -AsOfDate "2025-12-06"
```

**Диагностика файлов (пример вывода `-Verbose -WhatIf`):**
```
=== Wine Assistant - Daily Import ===
Repo root:       D:\...\wine-assistant
Supplier:        dreemwine

PowerShell: 5.1.26100.7462
Python: D:\...\wine-assistant\.venv\Scripts\python.exe
Mode:            auto-discovery
Inbox:           D:\...\wine-assistant\data\inbox

Scanning inbox: D:\...\wine-assistant\data\inbox
Top candidates (sorted):
 1) 2025_12_10 Прайс_Легенда_Виноделия.xlsx | parsed_date=2025-12-10 | last_write=2025-12-24 13:42:00
 2) 2025_12_03 Прайс_Легенда_Виноделия.xlsx | parsed_date=2025-12-03 | last_write=2025-12-03 11:00:00
 3) 2025_12_02 Прайс_Легенда_Виноделия.xlsx | parsed_date=2025-12-02 | last_write=2025-12-24 13:42:00
Chosen file: D:\...\2025_12_10 Прайс_Легенда_Виноделия.xlsx
Selected file:   2025_12_10 Прайс_Легенда_Виноделия.xlsx
Selected full path: D:\...\2025_12_10 Прайс_Легенда_Виноделия.xlsx
as_of_date:      2025-12-10 (from filename)
as_of_date source: filename (override via -AsOfDate to change)
Command:        "D:\...\.venv\Scripts\python.exe" -m scripts.run_import_orchestrator --supplier dreemwine --file "..." --as-of-date 2025-12-10 --import-fn scripts.import_targets.run_daily_adapter:import_with_run_daily

WHATIF: import orchestrator will NOT be executed.
WHATIF: command       = "..." -m scripts.run_import_orchestrator ...
WHATIF: supplier      = dreemwine
WHATIF: selected file = D:\...\2025_12_10 Прайс_Легенда_Виноделия.xlsx
WHATIF: as_of_date    = 2025-12-10
```

### Ручной запуск orchestrator

```powershell
python -m scripts.run_import_orchestrator `
  --supplier "dreemwine" `
  --file "data/inbox/2025_12_10 Прайс_Легенда_Виноделия.xlsx" `
  --as-of-date "2025-12-10" `
  --import-fn "scripts.import_targets.run_daily_adapter:import_with_run_daily"

# Expected output:
# INFO import_run_success metrics={'total_rows_processed': 262, 'rows_skipped': 298}
```

### Проверка в БД

```powershell
# Последние импорты
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, as_of_date, status,
       total_rows_processed, rows_skipped, envelope_id, created_at
FROM import_runs
ORDER BY created_at DESC LIMIT 10;"

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
```

### Автоматизация (Task Scheduler)

```powershell
# Daily import (09:00)
$taskName = "wine-assistant daily import"
$scriptPath = (Resolve-Path ".\scripts\run_daily_import.ps1").Path
schtasks /Create /TN $taskName /SC DAILY /ST 09:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Supplier dreemwine" /F

# Stale detector (every 15 minutes)
$taskName = "wine-assistant stale detector"
$scriptPath = (Resolve-Path ".\scripts\run_stale_detector.ps1").Path
schtasks /Create /TN $taskName /SC MINUTE /MO 15 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" /F

# Verify tasks
Get-ScheduledTaskInfo -TaskName "wine-assistant daily import"
Get-ScheduledTaskInfo -TaskName "wine-assistant stale detector"
```

### Troubleshooting

**Problem: Import failed**
```powershell
# Check error details
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, error_summary, error_details
FROM import_runs
WHERE status = 'failed'
ORDER BY created_at DESC LIMIT 1;"

# Retry after fix (same command)
python -m scripts.run_import_orchestrator ...
```

**Problem: Wrong file selected**
```powershell
# Диагностика: проверить какой файл будет выбран
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose -WhatIf

# Output покажет топ-5 кандидатов и выбранный файл (см. пример выше)

# Решение: явно указать файл
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -FilePath "data/inbox/specific_file.xlsx"
```

**Problem: Import stuck (running > 2 hours)**
```powershell
# Check stuck runs
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, started_at,
       EXTRACT(EPOCH FROM (NOW() - started_at))/60 as minutes_stuck
FROM import_runs
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '2 hours';"

# Dry-run: проверить что будет сделано
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -Verbose -WhatIf

# Реальный запуск с диагностикой
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -Verbose

# Без диагностики (как раньше)
.\scripts\run_stale_detector.ps1 -RunningMinutes 120
```

**Problem: Data staleness > 24h**
```powershell
# Check stale suppliers
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT supplier, hours_since_success, last_success_at
FROM v_import_staleness
WHERE hours_since_success > 24;"

# Check file availability
Get-ChildItem "data/inbox/*.xlsx" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5

# Trigger manual import
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
```

### Stale Detector (зависшие импорты)

```powershell
# Dry-run: проверить параметры и команду без запуска
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose -WhatIf
```

**Expected output:**
```
=== Wine Assistant - Stale Import Runs Detector ===
Repo root:       D:\...\wine-assistant
RunningMinutes:  120
PendingMinutes:  15

PowerShell: 5.1.26100.7462
Python: D:\...\wine-assistant\.venv\Scripts\python.exe
Command:        "D:\...\.venv\Scripts\python.exe" -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
WHATIF: stale detector will NOT be executed.
WHATIF: command        = "..." -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
WHATIF: RunningMinutes = 120
WHATIF: PendingMinutes = 15
```

**Реальный запуск с диагностикой:**
```powershell
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose
```

**Expected output:**
```
=== Wine Assistant - Stale Import Runs Detector ===
Repo root:       D:\...\wine-assistant
RunningMinutes:  120
PendingMinutes:  15

PowerShell: 5.1.26100.7462
Python: D:\...\wine-assistant\.venv\Scripts\python.exe
Command:        "..." -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
Running stale detector...

2025-12-26 08:58:57,299 INFO __main__ stale_import_runs_done rolled_back_running=0 rolled_back_pending=0

Stale detector completed successfully.
```

**Тихий запуск (без диагностики):**
```powershell
.\scripts\run_stale_detector.ps1
```

**Диагностика stale detector:**
- `-Verbose` — показывает версии PowerShell/Python, команду запуска
- `-WhatIf` — не запускает detector, только показывает параметры
- `-RunningMinutes` — порог для stuck "running" импортов (default: 120)
- `-PendingMinutes` — порог для stuck "pending" импортов (default: 15)

### Monitoring Queries

```powershell
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

# Import duration trend
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT DATE(finished_at) as import_date,
       AVG(EXTRACT(EPOCH FROM (finished_at - started_at)))::INT as avg_duration_sec,
       MAX(EXTRACT(EPOCH FROM (finished_at - started_at)))::INT as max_duration_sec
FROM import_runs
WHERE status = 'success'
  AND finished_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(finished_at)
ORDER BY import_date DESC
LIMIT 10;"
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

---

## 📚 Полезные ссылки

- **API Swagger:** http://localhost:18000/docs
- **Adminer:** http://localhost:18080
- **Grafana:** http://localhost:15000 (admin/admin)
- **Backup/DR Dashboard:** http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
- **GitHub:** https://github.com/glinozem/wine-assistant

---

**Создано:** 04 декабря 2025
**Обновлено:** 26 декабря 2025 (точные примеры вывода для Verbose/WhatIf)
**Версия:** 1.4-final
**Для:** Wine Assistant v0.5.0+ (M1 Complete)
