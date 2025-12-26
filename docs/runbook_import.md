# Runbook: импорт прайс-листов (операционный)

## 0) Предварительные условия

- `docker compose up -d` поднял сервисы, включая `db`.
- Активировано виртуальное окружение (или `python` указывает на venv):
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- В `data/inbox/` лежит прайс поставщика в формате Excel.
  Рекомендованный формат имени: `YYYY_MM_DD ... .xlsx`.

## 1) Стандартный путь (дежурный запуск)

```powershell
# Простейший вариант
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"

# С диагностикой (показывает топ-5 кандидатов + выбранный файл)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose

# Dry-run (не запускает импорт, только показывает что будет сделано)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose -WhatIf
```

Скрипт:
- выберет последний файл по **дате в имени** `YYYY_MM_DD`,
- определит `as_of_date` из имени,
- запустит orchestrator.

**Диагностика файлов:**
- `-Verbose` — показывает топ-5 кандидатов с датами из имени и LastWriteTime:
  ```
  VERBOSE: Top candidates (sorted):
  VERBOSE:  1) 2025_12_10 Прайс... | parsed_date=2025-12-10 | last_write=2025-12-24 13:42:00
  VERBOSE:  2) 2025_12_03 Прайс... | parsed_date=2025-12-03 | last_write=2025-12-03 11:00:00
  VERBOSE: Chosen file: D:\...\2025_12_10 Прайс_Легенда_Виноделия.xlsx
  ```
- `-WhatIf` — не запускает импорт, только показывает выбранный файл и as_of_date:
  ```
  WHATIF: orchestrator will NOT be executed.
  WHATIF: selected file = D:\...\2025_12_10 Прайс_Легенда_Виноделия.xlsx
  WHATIF: as_of_date     = 2025-12-10
  ```

## 2) Типовые SQL-проверки

### 2.1 Последние прогоны

```powershell
docker compose exec -T db psql -U postgres -d wine_db -c `
  "select run_id, status, supplier, as_of_date, file_sha256, envelope_id,
          total_rows_processed, rows_skipped, created_at
   from import_runs
   order by created_at desc
   limit 20;"
```

### 2.2 Проверка «idempotency-скипа»

Ожидаемое поведение: при повторе **того же файла** (тот же sha256) для того же `as_of_date`
создаётся `status=skipped`, при этом `envelope_id` совпадает с последним `success`.

```powershell
docker compose exec -T db psql -U postgres -d wine_db -c `
  "select run_id, status, as_of_date, file_sha256, envelope_id, created_at
   from import_runs
   where supplier='dreemwine' and as_of_date='2025-12-10'
   order by created_at desc;"
```

**Пример результата:**
```
                run_id                | status  | as_of_date |            file_sha256            |             envelope_id
--------------------------------------+---------+------------+-----------------------------------+--------------------------------------
 7273eabf-ac5c-4a1f-9b59-982eef6c7520 | skipped | 2025-12-10 | e8b0...                          | 6a8a99ff-e01d-412e-8ebd-60da5defd2f6
 153a53b0-4002-41e8-9111-a33d9b0b5333 | success | 2025-12-10 | e8b0...                          | 6a8a99ff-e01d-412e-8ebd-60da5defd2f6
```

Обратите внимание: `envelope_id` одинаковый, что подтверждает идемпотентность.

## 3) Частые проблемы и что делать

### 3.1 Ошибка partition: `effective_from = null`

Симптом (раньше встречалось): `no partition ... effective_from = (null)`.

Причина: ETL писал цену без `effective_from`.
Решение уже внесено в `etl/run_daily.py`: `effective_from` всегда вычисляется из `as_of_date` (или `as_of_datetime`).

### 3.2 ETL produced 0 valid rows

Симптом: `ETL produced 0 valid rows. Check sheet name and mapping_template.json ...`

Чаще всего:
- неверное имя sheet,
- неправильный `header_row`,
- колонки в прайсе поменялись и mapping не «сходится».

Действия:
1) проверить `etl/mapping_template.json` (sheet/header_row/columns),
2) вывести колонки через pandas (см. QUICK_REFERENCE),
3) при необходимости обновить mapping.

### 3.3 Неправильный файл выбран

Симптом: скрипт выбирает не тот файл, который вы ожидали.

Диагностика:
```powershell
# Посмотреть какой файл будет выбран (без запуска импорта)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose -WhatIf
```

Output покажет:
- Топ-5 кандидатов с датами
- Выбранный файл
- Извлечённый as_of_date

Решение:
```powershell
# Явно указать нужный файл
.\scripts\run_daily_import.ps1 `
  -Supplier "dreemwine" `
  -FilePath "data/inbox/2025_12_03 Прайс_Легенда_Виноделия.xlsx"

# Или override as_of_date
.\scripts\run_daily_import.ps1 `
  -Supplier "dreemwine" `
  -AsOfDate "2025-12-03"
```

### 3.4 Envelope не создаётся / падает вставка

Envelope создаётся best-effort.
Если `public.ingest_envelope` отсутствует или schema требует NOT NULL без defaults — envelope будет `None`, но импорт продолжится.

Если envelope существует, но файл уже был загружен ранее, возможен `UniqueViolation(file_sha256)`.
В этом случае код делает lookup по sha256 и возвращает существующий `envelope_id`.

## 4) Детектор «зависших» импортов

### Dry-run (проверка без запуска)

```powershell
# Проверить параметры и команду без запуска
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose -WhatIf
```

**Expected output:**
```
=== Wine Assistant - Stale Import Runs Detector ===
Repo root:       D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
RunningMinutes:  120
PendingMinutes:  15

VERBOSE: PowerShell: 5.1.26100.7462
VERBOSE: Python: D:\...\wine-assistant\.venv\Scripts\python.exe
VERBOSE: Command: "..." -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
WHATIF: stale detector will NOT be executed.
WHATIF: command = "..." -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
WHATIF: RunningMinutes = 120
WHATIF: PendingMinutes = 15
```

### Реальный запуск с диагностикой

```powershell
# Запуск с диагностикой
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose
```

**Expected output:**
```
=== Wine Assistant - Stale Import Runs Detector ===
Repo root:       D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant
RunningMinutes:  120
PendingMinutes:  15

VERBOSE: PowerShell: 5.1.26100.7462
VERBOSE: Python: D:\...\wine-assistant\.venv\Scripts\python.exe
VERBOSE: Command: "..." -m scripts.mark_stale_import_runs --running-minutes 120 --pending-minutes 15
Running stale detector...

2025-12-26 08:58:57,299 INFO __main__ stale_import_runs_done rolled_back_running=0 rolled_back_pending=0

Stale detector completed successfully.
```

### Тихий запуск (без диагностики)

```powershell
# Defaults: RunningMinutes=120, PendingMinutes=15
.\scripts\run_stale_detector.ps1
```

**Назначение:** найти `import_runs` со статусом `running` или `pending`, которые висят дольше порога, и перевести в `rolled_back`.

**Параметры:**
- `-RunningMinutes` — порог для stuck "running" импортов (default: 120)
- `-PendingMinutes` — порог для stuck "pending" импортов (default: 15)
- `-Verbose` — показывает версии PowerShell/Python, команду запуска
- `-WhatIf` — не запускает detector, только показывает параметры

## 5) Примечание по семантике `as_of_date`

`as_of_date` — бизнес-дата «эффективности» цен (используется как `effective_from` в `product_prices`).

По умолчанию `run_daily_import.ps1` берёт её из имени файла (`YYYY_MM_DD` → `YYYY-MM-DD`), но вы можете override'ить `-AsOfDate`.

**Пример:**
```powershell
# Файл: 2025_12_10 Прайс...xlsx
# as_of_date автоматически: 2025-12-10

# Override (если бизнес-дата отличается от даты в имени):
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -AsOfDate "2025-12-06"
```

## 6) Типичные сценарии

### 6.1 Первый импорт новой даты

```powershell
# 1. Проверить что файл появился
Get-ChildItem "data/inbox/2025_12_24*.xlsx"

# 2. Dry-run для проверки
.\scripts\run_daily_import.ps1 -Supplier "dreemwine" -Verbose -WhatIf

# 3. Запустить импорт
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"

# 4. Проверить результат
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, status, total_rows_processed, rows_skipped
FROM import_runs
ORDER BY created_at DESC LIMIT 1;"
```

### 6.2 Повторный импорт (идемпотентность)

```powershell
# Повторный запуск той же команды
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"

# Expected output:
# INFO import_orchestrator: skip. reason=SKIP_ALREADY_SUCCESS
# INFO Created skipped attempt ... (SKIP_ALREADY_SUCCESS: ...)

# Проверка в БД - должно быть 2 записи: success + skipped
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT status, COUNT(*) as count
FROM import_runs
WHERE supplier='dreemwine' AND as_of_date='2025-12-10'
GROUP BY status;"
```

**Expected result:**
```
  status  | count
----------+-------
 success  |     1
 skipped  |     1
```

### 6.3 Retry failed импорта

```powershell
# 1. Проверить ошибку
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, error_summary, error_details
FROM import_runs
WHERE status = 'failed'
ORDER BY created_at DESC LIMIT 1;"

# 2. Исправить проблему (например, обновить mapping)

# 3. Retry (той же командой)
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
# Orchestrator создаст новую попытку для той же (supplier, as_of_date, file_sha256)
```

### 6.4 Cleanup зависших импортов

```powershell
# 1. Найти зависшие импорты
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, status, started_at,
       EXTRACT(EPOCH FROM (NOW() - started_at))/60 as minutes_running
FROM import_runs
WHERE status IN ('running', 'pending')
ORDER BY started_at;"

# 2. Dry-run stale detector
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose -WhatIf

# Output:
# WHATIF: stale detector will NOT be executed.
# WHATIF: RunningMinutes = 120
# WHATIF: PendingMinutes = 15

# 3. Запустить cleanup
.\scripts\run_stale_detector.ps1 -RunningMinutes 120 -PendingMinutes 15 -Verbose

# Output:
# 2025-12-26 08:58:57,299 INFO stale_import_runs_done rolled_back_running=0 rolled_back_pending=0

# 4. Проверить результат
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT status, COUNT(*) as count
FROM import_runs
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY status;"
```

---

**Обновлено:** 26 декабря 2025
**Версия:** 1.2
**Добавлено:** Verbose/WhatIf для stale detector, expected output, сценарий cleanup
