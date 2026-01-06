# Changelog

## [Unreleased]

### Added

#### Daily Import v1.0.4 (Production Ready)

Операционный “daily import” приведён к повторяемому и предсказуемому процессу: от обнаружения файлов в `data/inbox/` до архивирования/карантина и фиксации истории запусков.

- **Ops API (Daily Import)**
  - `GET /api/v1/ops/daily-import/inbox` — список файлов в `data/inbox/` (с признаком newest).
  - `POST /api/v1/ops/daily-import/run` — старт запуска (mode: `auto` | `files`).
  - `GET /api/v1/ops/daily-import/runs/<run_id>` — детали запуска + результаты по каждому файлу.
  - `GET /api/v1/ops/files/{archive|quarantine}/<relative_path>` — скачивание файлов архива/карантина (если endpoint включён в API).

- **Ops UI (Daily Import)**
  - HTML UI: `api/templates/daily_import.html`.
  - Роут: `GET /daily-import` (рендер шаблона; API ключ можно подставлять из `API_KEY`).

- **Orchestrator: scripts/daily_import_ops.py**
  - Запуск внутри контейнера: `python -m scripts.daily_import_ops --mode auto|files [--files ...]`.
  - Режимы:
    - `auto` — берёт самый новый `.xlsx` в `data/inbox/` (selected_mode=`AUTO_INBOX_NEWEST`).
    - `files` — обрабатывает явный список файлов (selected_mode=`MANUAL_LIST`).
  - Результат: JSON-отчёт (`run_id`, `status`, `summary`, `files[]`), сохраняемый также в `data/logs/daily-import/<run_id>.json`.

#### Makefile targets

- `make inbox-ls` — показать `.xlsx` в `data/inbox/` (внутри контейнера).
- `make daily-import` — запуск `auto` (newest).
- `make daily-import-files FILES="file1.xlsx file2.xlsx"` — запуск `files` (ВАЖНО: Makefile таргет не подходит для имён с пробелами/кириллицей; на Windows используйте wrapper ниже).
- `make daily-import-history` — последние 10 JSON-логов запусков.
- `make daily-import-show RUN_ID=<uuid>` — показать JSON по конкретному запуску.
- `make daily-import-cleanup-archive DAYS=90` — очистка архива старше N дней.
- `make daily-import-quarantine-stats` — базовая статистика по карантину.

Windows-friendly wrappers (Makefile + PowerShell):

- `make daily-import-ps` — запуск `auto` через `scripts/run_daily_import.ps1`.
- `make daily-import-files-ps FILES="Имя 1.xlsx,Имя 2.xlsx"` — запуск `files` через `scripts/run_daily_import.ps1` (CSV; устойчиво к пробелам и кириллице).

#### PowerShell wrapper (Windows): scripts/run_daily_import.ps1

- Параметры: `-Mode auto|files`, `-Files` (массив или одна строка CSV).
- Запускает orchestrator в контейнере через `docker compose exec -T api ...` (без `bash -c`, чтобы минимизировать quoting-проблемы).
- Пытается устойчиво извлечь JSON из stdout/stderr (перебирает позиции `{` до успешного `ConvertFrom-Json`).
- Exit codes:
  - `0` — OK / OK_WITH_SKIPS без карантина,
  - `1` — есть `QUARANTINED`,
  - `2` — `FAILED` / `TIMEOUT`,
  - `4` — `NO_FILES_IN_INBOX`,
  - `5` — не удалось распарсить JSON.

#### Encoding fixes (UTF-8)

- Docker/Compose фиксируют UTF-8 окружение (LANG/LC_ALL/PYTHONUTF8/PYTHONIOENCODING), чтобы кириллица и Unicode-символы корректно логировались в контейнере и при проксировании вывода в PowerShell/CI.


### Changed
- `scripts/cleanup_test_data.py` — утилита очистки тестовых/интеграционных данных в Postgres (dry-run по умолчанию, `--apply` для выполнения)

- UI `/ui`: бесконечная прокрутка и корректная загрузка всех позиций поверх пагинации (`limit/offset`), а не только первой страницы

- Документация: обновлены команды PowerShell для вызовов API (`Invoke-RestMethod` / `curl.exe`), добавлены примеры очистки тестовых данных

- **`project-structure.txt`** — обновлена структура с учётом observability файлов

- **`etl/run_daily.py`** — интегрирован с Import Orchestrator (#165, #173)
  - Принимает `conn` parameter для transaction control (R0.2)
  - Возвращает structured metrics/artifacts dict
  - Auto `as_of_date`/`as_of_datetime` support через argument
  - Production mapping: `etl/mapping_template.json` (DreemWine: sheet="Основной", header_row=3)
  - **Inventory tracking:** upsert в `inventory` + snapshot в `inventory_history`
  - **Supplier normalization:** norm_supplier_key() для supplier field
  - **Extended prices:** price_list_rub, price_final_rub, price_rub с fallback логикой

### Fixed

#### v1.0.4 Bugfix (Windows CP1251 Encoding) ✅
- **UnicodeEncodeError на Windows console** — RESOLVED
  - Добавлена функция `safe_print()` в 4 скрипта:
    - `scripts/load_wineries.py`
    - `scripts/enrich_producers.py`
    - `scripts/sync_inventory_history.py`
    - `scripts/daily_import_ops.py` (новый файл)
  - Использует `import builtins` (canonical approach)
  - Graceful fallback: CP1251 encoding с `errors='replace'`
  - Emoji отображаются как `?` на CP1251 console (expected behavior)
  - **Testing:** 15+ consecutive successful runs, exit code 0
  - **Tag:** v1.0.4
  - **PR:** #172

- Тесты: скорректирован unit-тест, который проверяет приоритет `df.attrs['prefer_discount_cell']` над `PREFER_S5` (в `scripts/load_utils.py` логика уже корректна)

- DR smoke test: file locking issues на Windows при использовании Promtail

- **Import Operations:** UUID serialization для Windows/psycopg2 compatibility (#165)
  - `envelope_id` теперь корректно сериализуется в psycopg2 на Windows

- **Import Operations:** `envelope_id` сохраняется в skipped attempts для full audit trail (#165)
  - Раньше skipped attempts не имели envelope_id
  - Теперь envelope_id копируется из success attempt для полной трассировки

## v0.4.3

* docs: update documentation for Sprint 4a (v0.5.0) (#89) (67f36fe) by glinozem
* feat(etl): implement automated daily import scheduler (#88) (7e32e9c) by glinozem
* feat: implement automatic date extraction from Excel and filenames (#81) (#87) (1d300ab) by glinozem
* feat: Implement file fingerprinting for ETL idempotency (#80) (#86) (8d40c40) by glinozem
* add Russian translations for README and roadmap (#79) (eb8dd45) by glinozem
* docs: Roadmap v2 (Sprint 7+) (#78) (f64b22f) by glinozem
* docs: add roadmap for Sprint 7-9 (business integration) (#77) (8dc9115) by glinozem
* test(load_csv): add 5 tests for _get_discount_from_cell() function (#76) (7a6b73e) by glinozem
* docs: add coverage badge and fix README encoding (#75) (a3f8e37) by glinozem
* test: add unit tests for load_csv.py utility functions (#58) (#74) (0cc4ed9) by glinozem
* Fix/readme and workflow v2 (#73) (b297d31) by glinozem
* docs(changelog): add CHANGELOG for v0.4.0 (#52) (b31c9e6) by glinozem
* fix: Restore README.md with proper UTF-8 encoding (#72) (e853bb6) by glinozem
* fix: Fix README.md encoding (UTF-8 without BOM) (#71) (6f9780a) by glinozem
* feat(testing): Setup pytest infrastructure (Issue #57) (#70) (d0a646c) by glinozem
* Feature/structured logging (#55) (73c8480) by glinozem
* docs(changelog): add CHANGELOG for v0.4.1 (#54) (d26e421) by glinozem
