# PR-4 Checklist: docs + automation scripts for Import Orchestrator

## A) Документация

- [ ] Все документы размещены вместе (рекомендуемо: `docs/dev/import/`), ссылки между ними работают:
  - [ ] `INDEX.md`
  - [ ] `QUICK_REFERENCE.md`
  - [ ] `import_flow.md`
  - [ ] `runbook_import.md`
  - [ ] `INTEGRATION_INSTRUCTIONS.md`
  - [ ] `CHANGELOG.md`
  - [ ] `PR4_CHECKLIST.md`
- [ ] Нет ссылок на условные пути/файлы:
  - [ ] нет placeholder-имен файлов
  - [ ] нет Linux-специфичных абсолютных путей
- [ ] Примеры отражают текущую семантику:
  - [ ] idempotency-ключ: `(supplier, as_of_date, file_sha256)`
  - [ ] метрики: `total_rows_processed`, `rows_skipped`
  - [ ] `envelope_id` сохраняется и у `skipped` попыток (фикс PR-3)
- [ ] DreemWine mapping описан корректно:
  - [ ] `etl/mapping_template.json`: `sheet="Основной"`, `header_row=3`

## B) Скрипты

### B1) run_daily_import.ps1

- [ ] Скрипт лежит в `scripts/run_daily_import.ps1`
- [ ] По умолчанию ищет `.xlsx` в `data/inbox/` по паттерну даты имени `????_??_??*.xlsx`
- [ ] Исключает временные файлы Excel `~$*.xlsx`
- [ ] Выбирает «последний» файл по дате из имени (`YYYY_MM_DD`), fallback по `LastWriteTime`
- [ ] `as_of_date` по умолчанию извлекается из имени файла (можно override через `-AsOfDate`)
- [ ] Запуск из корня репозитория работает:
  ```powershell
  .\scripts\run_daily_import.ps1 -Supplier "dreemwine"
  ```

### B2) run_stale_detector.ps1

- [ ] Скрипт лежит в `scripts/run_stale_detector.ps1`
- [ ] Запуск вручную работает:
  ```powershell
  .\scripts\run_stale_detector.ps1 -RunningMinutes 120
  ```

## C) Функциональная валидация (на реальном файле)

1) Импорт:
```powershell
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
```

2) Повтор (idempotency):
```powershell
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
```
Ожидаемо: второй запуск даёт `status=skipped`, при этом `envelope_id` тот же, что и у последнего `success`.

3) DB-проверка:
```powershell
docker compose exec -T db psql -U postgres -d wine_db -c `
  "select run_id, status, as_of_date, file_sha256, envelope_id, total_rows_processed, rows_skipped, created_at
   from import_runs
   where supplier='dreemwine'
   order by created_at desc
   limit 10;"
```

4) Проверка «двух записей на одну тройку» (ожидаемо: `success + skipped`):
```powershell
docker compose exec -T db psql -U postgres -d wine_db -c `
  "select supplier, as_of_date, file_sha256, count(*)
   from import_runs
   group by supplier, as_of_date, file_sha256
   having count(*) > 1
   order by count(*) desc
   limit 20;"
```
