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
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
```

Скрипт:
- выберет последний файл по **дате в имени** `YYYY_MM_DD`,
- определит `as_of_date` из имени,
- запустит orchestrator.

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

### 3.3 Envelope не создаётся / падает вставка

Envelope создаётся best-effort.
Если `public.ingest_envelope` отсутствует или schema требует NOT NULL без defaults — envelope будет `None`, но импорт продолжится.

Если envelope существует, но файл уже был загружен ранее, возможен `UniqueViolation(file_sha256)`.
В этом случае код делает lookup по sha256 и возвращает существующий `envelope_id`.

## 4) Детектор «зависших» импортов

Запуск вручную:

```powershell
.\scripts\run_stale_detector.ps1 -RunningMinutes 120
```

Назначение: найти `import_runs` со статусом `running`, которые висят дольше порога, и перевести в `stale/rolled_back` (согласно политике проекта).

## 5) Примечание по семантике `as_of_date`

`as_of_date` — бизнес-дата «эффективности» цен (используется как `effective_from` в `product_prices`).

По умолчанию `run_daily_import.ps1` берёт её из имени файла (`YYYY_MM_DD` → `YYYY-MM-DD`), но вы можете override'ить `-AsOfDate`.
