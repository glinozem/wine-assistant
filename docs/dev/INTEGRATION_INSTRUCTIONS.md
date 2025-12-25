# PR-4: интеграция документации и скриптов

Этот документ описывает, как интегрировать пакет PR-4 в репозиторий так, чтобы он соответствовал текущему состоянию кода.

## 1) Размещение файлов

Рекомендованное расположение (чтобы ссылки работали «из коробки»):

- Документация: `docs/dev/import/`
  - `INDEX.md`
  - `QUICK_REFERENCE.md`
  - `import_flow.md`
  - `runbook_import.md`
  - `PR4_CHECKLIST.md`
  - `CHANGELOG.md`
  - `INTEGRATION_INSTRUCTIONS.md` (этот файл)

- Скрипты:
  - `scripts/run_daily_import.ps1`
  - `scripts/run_stale_detector.ps1`

## 2) Обновление README.md

В `README.md`:
- добавить (или обновить) раздел про импорт прайсов,
- вставить ссылку на `docs/dev/import/INDEX.md`.

## 3) Локальная проверка перед PR

```powershell
ruff check .
pytest -q
```

### 3.1 Ручной импорт (как smoke)

```powershell
.\scripts\run_daily_import.ps1 -Supplier "dreemwine"
```

### 3.2 Проверка метрик в БД

```powershell
docker compose exec -T db psql -U postgres -d wine_db -c `
  "select run_id, status, as_of_date, total_rows_processed, rows_skipped, envelope_id
   from import_runs
   where supplier='dreemwine'
   order by created_at desc
   limit 10;"
```

### 3.3 Проверка idempotency (повтор)

Повторить тот же импорт (тем же файлом). Ожидаемо:
- создаётся `status=skipped`,
- `envelope_id` совпадает с last success.

## 4) Рекомендация по структуре коммита (PR-4)

- `feat(docs): add import operations documentation`
- `feat(scripts): add daily import + stale detector wrappers`

Если вы добавляете всё одним коммитом — убедитесь, что:
- нет ссылок на условные файлы с placeholder-именами файлов,
- нет Linux-специфичных абсолютных путей,
- примеры соответствуют DreemWine mapping (`sheet="Основной"`, `header_row=3`),
- в примерах используются метрики `total_rows_processed` и `rows_skipped`.
