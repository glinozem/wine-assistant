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

## 📥 Daily Import v1.0.4 (Production Ready) 🎉

### Инкрементный ежедневный импорт

**Новый workflow** — incremental imports без wipe volumes.

**Ключевые фичи:**
- ✅ Auto-inbox: автоматический выбор новейшего файла
- ✅ Idempotent: безопасен для повторного запуска
- ✅ Inventory tracking: автоматические snapshot'ы
- ✅ Windows-friendly: UnicodeEncodeError исправлен (v1.0.4)

### Простейший вариант (рекомендуется)

```powershell
# Auto-inbox: автоматически берет новейший .xlsx из data/inbox
make daily-import

# Или через Python напрямую
python -m scripts.daily_import --inbox data/inbox

# Или PowerShell wrapper
.\scripts\run_daily_import.ps1
```

### С параметрами

```powershell
# Explicit files list
make daily-import-files FILES="data/inbox/2025_12_10.xlsx data/inbox/2025_12_17.xlsx"

# Или через Python
python -m scripts.daily_import --files data/inbox/2025_12_10.xlsx data/inbox/2025_12_17.xlsx

# Или PowerShell
.\scripts\run_daily_import.ps1 -Files data\inbox\2025_12_10.xlsx, data\inbox\2025_12_17.xlsx

# Custom directories
python -m scripts.daily_import `
  --inbox D:\imports\inbox `
  --archive D:\imports\archive `
  --quarantine D:\imports\quarantine

# Без inventory snapshot (редко)
python -m scripts.daily_import --no-snapshot

# Snapshot dry-run first (проверка перед применением)
.\scripts\run_daily_import.ps1 -SnapshotDryRunFirst
```

### Expected Output

**Успешный импорт:**
```
=== IMPORT (load_csv) ===
>>> File: data\inbox\2025_12_12 Прайс_Легенда_Виноделия.xlsx
[OK] Import completed successfully
[daily-import] Moved: data\inbox\*.xlsx -> data\archive\2025-12\*.xlsx

=== LOAD WINERIES CATALOG ===
Готово. Вставлено новых записей: 0, обновлено существующих: 46

=== ENRICH PRODUCTS ===
Готово. Всего затронуто строк в products: 244

=== MAINTENANCE SQL ===
[daily-import] Maintenance SQL completed

=== INVENTORY HISTORY SNAPSHOT ===
[OK] Вставлено 270 записей в public.inventory_history

=== SUMMARY ===
- IMPORTED 2025_12_12 Прайс_Легенда_Виноделия.xlsx

Exit code: 0
```

**Идемпотентность (SKIP):**
```
=== IMPORT (load_csv) ===
>> SKIP: File already imported
[daily-import] Moved: data\inbox\*.xlsx -> data\archive\2025-12\*.xlsx

=== SUMMARY ===
- SKIPPED (already imported)

Exit code: 0
```

### Проверка в БД

```powershell
# Последние импорты
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, as_of_date, status,
       total_rows_processed, rows_skipped, envelope_id, created_at
FROM import_runs
ORDER BY created_at DESC LIMIT 10;"

# Inventory snapshots
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT COUNT(*) as total_snapshots,
       MAX(as_of) as latest_snapshot,
       COUNT(DISTINCT code) as unique_products
FROM inventory_history;"

# Current inventory
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT COUNT(*) as total_products,
       SUM(stock_total) as total_stock,
       SUM(stock_free) as free_stock,
       MAX(asof_date) as snapshot_date
FROM inventory;"

# Products with inventory
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT p.code, p.title_ru, p.supplier,
       i.stock_total, i.reserved, i.stock_free,
       i.asof_date
FROM products p
JOIN inventory i ON p.code = i.code
WHERE i.stock_total > 0
ORDER BY i.stock_total DESC
LIMIT 10;"
```

### Automation (Task Scheduler)

```powershell
# Daily import (09:00)
$taskName = "wine-assistant daily import"
$scriptPath = (Resolve-Path ".\scripts\run_daily_import.ps1").Path
schtasks /Create /TN $taskName /SC DAILY /ST 09:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" /F

# Verify task
Get-ScheduledTaskInfo -TaskName "wine-assistant daily import"

# Manual trigger
Start-ScheduledTask -TaskName "wine-assistant daily import"
```

### Inventory Snapshots

```powershell
# Manual snapshot with custom date
make sync-inventory-history AS_OF="2025-12-31"

# Dry-run first
make sync-inventory-history-dry-run AS_OF="2025-12-31"

# Via Python
python -m scripts.sync_inventory_history --as-of "2025-12-31T23:59:59"
python -m scripts.sync_inventory_history --dry-run --as-of "2025-12-31"
```

### Troubleshooting

**Problem: UnicodeEncodeError**
```powershell
# Verify v1.0.4 safe_print() is present
grep "def safe_print" scripts/daily_import.py
grep "def safe_print" scripts/load_wineries.py
grep "def safe_print" scripts/enrich_producers.py
grep "def safe_print" scripts/sync_inventory_history.py

# All 4 files should have the function
# If not, update to v1.0.4
```

**Problem: Import failed**
```powershell
# Check quarantine directory
Get-ChildItem data/quarantine -Recurse | Select-Object FullName, Length, LastWriteTime

# Check error in database
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, error_summary, error_details, created_at
FROM import_runs
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 1;"

# Review file and fix issue
# Move file back to inbox
Move-Item data/quarantine/2025-12/problematic_file.xlsx data/inbox/

# Retry import
python -m scripts.daily_import --inbox data/inbox
```

**Problem: Wrong file selected (auto-inbox)**
```powershell
# Check what file will be selected
Get-ChildItem data/inbox/*.xlsx |
  Sort-Object LastWriteTime -Descending |
  Select-Object Name, LastWriteTime -First 5

# Solution: Use explicit files mode
python -m scripts.daily_import --files data/inbox/specific_file.xlsx
```

**Problem: Advisory lock stuck**
```powershell
# Check locks
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT * FROM pg_locks WHERE locktype = 'advisory';"

# Release all advisory locks
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT pg_advisory_unlock_all();"

# Retry import
python -m scripts.daily_import
```

**Problem: Inventory snapshot not created**
```powershell
# Expected: snapshot only created on actual import, not on SKIP
# Check if file was SKIP
# Review output for ">> SKIP: File already imported"

# Manual snapshot if needed
make sync-inventory-history AS_OF="2025-12-31"
```

**Problem: Emoji shows as '?' in console**
```
Expected behavior on Windows CP1251 console
Not an error - this is correct safe_print() behavior

Workaround: Use UTF-8 terminal or run `chcp 65001` first
```

### Fresh Deployment & Testing

```powershell
# Bootstrap from scratch (wipe volumes + rebuild)
.\scripts\bootstrap_from_scratch.ps1 -RebuildImages

# E2E smoke test
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1

# Or direct PowerShell
.\scripts\smoke_e2e.ps1 -Supplier dreemwine -Fresh -Build
```

---

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

```powershell
# Check exit code
echo $LASTEXITCODE  # Should be 0

# Review output for errors
python -m scripts.daily_import --inbox data/inbox

# Check quarantine
Get-ChildItem data/quarantine -Recurse

# Review database
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT * FROM import_runs WHERE status = 'failed' ORDER BY created_at DESC LIMIT 1;"
```

---

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
**Обновлено:** 31 декабря 2025 (Daily Import v1.0.4)
**Версия:** 2.0
**Для:** Wine Assistant v0.5.0+ (M1 Complete + Daily Import v1.0.4)
