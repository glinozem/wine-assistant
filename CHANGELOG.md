# Changelog

## [Unreleased]

### Added

#### Daily Import v1.0.4 (Production Ready) 🎉

**Incremental Import Infrastructure**
- **`scripts/daily_import.py`** — новый orchestrator для ежедневного инкрементного импорта
  - Auto-inbox режим: автоматический выбор новейшего `.xlsx` файла из `data/inbox`
  - Explicit files режим: импорт конкретного списка файлов
  - Idempotent: безопасен для повторного запуска (SKIP уже импортированных файлов)
  - Advisory lock: предотвращает параллельное выполнение
  - Архивация: SUCCESS → `data/archive/YYYY-MM/`, ERROR → `data/quarantine/YYYY-MM/`
  - Полный пайплайн: import → wineries → enrichment → maintenance → inventory snapshot
  - PR: #173

**ETL & Inventory Enhancements**
- **Inventory tracking** в `etl/run_daily.py`
  - Поддержка колонок `stock_total`, `reserved`, `stock_free`
  - Функция `upsert_inventory()` для обновления текущих остатков
  - Идемпотентные snapshot'ы в `inventory_history` (один на дату)
  - Автоматическое вычисление `stock_free` если отсутствует

- **Supplier normalization**
  - Новое поле `supplier` в products table
  - Функция `norm_supplier_key()` для нормализации ключей поставщиков
  - Fallback логика: supplier → producer если не указан

- **Extended price tracking**
  - `price_list_rub` — прайсовая цена
  - `price_final_rub` — финальная цена со скидкой
  - `price_rub` — текущая цена (для обратной совместимости)
  - Fallback логика между полями

- **Mapping template updates** (`etl/mapping_template.json`)
  - Добавлены поля: `supplier`, `price_list_rub`, `price_final_rub`
  - Добавлены поля: `stock_total`, `reserved`, `stock_free`

**Automation & Testing Scripts**
- **`scripts/bootstrap_from_scratch.ps1`** — автоматизация fresh deployment
  - Wipes volumes (`docker compose down -v`)
  - Imports all price lists from inbox (sorted by date)
  - Loads wineries catalog
  - Enriches products with region/site
  - Backfills missing data
  - Creates inventory snapshot
  - Verification checks
  - Optional rebuild images flag
  - PR: #173

- **`scripts/smoke_e2e.ps1`** — end-to-end smoke testing
  - Full import workflow orchestration
  - Data integrity validation
  - Fresh mode support (wipe volumes)
  - Configurable stale detector
  - Optional API smoke tests
  - SQL validation checks
  - Makefile integration: `make smoke-e2e`
  - PR: #173

**Makefile Targets**
- `make daily-import` — auto-inbox (newest file only)
- `make daily-import-files FILES="..."` — explicit file list
- `make daily-import-ps1` — PowerShell wrapper
- `make sync-inventory-history AS_OF="..."` — inventory snapshot with custom date
- `make smoke-e2e` — E2E smoke tests with parameters
- PR: #173

**PowerShell Wrappers**
- **`scripts/run_daily_import.ps1`** — полностью переписан как thin wrapper
  - Упрощен с 214 строк до 64 строк
  - Прямой вызов `python -m scripts.daily_import`
  - Параметры: `-Files`, `-InboxPath`, `-NoSnapshot`, `-SnapshotDryRunFirst`
  - PR: #173

**Documentation**
- **`docs/changes_daily_import.md`** — документация daily import flow
  - Архитектура пайплайна
  - Режимы работы (auto-inbox, explicit files)
  - Правила архивации
  - Operational notes
  - PR: #173

#### Import Operations (M1 Complete) 🎉
- **Import orchestrator** — production-grade система импорта с полным аудитом
  - Registry `import_runs`: журналирование всех попыток импорта (success/failed/skipped/rolled_back)
  - Идемпотентность по ключу `(supplier, as_of_date, file_sha256)`
  - Views: `v_import_runs_summary`, `v_import_staleness` для мониторинга
  - Unique index предотвращает concurrent/duplicate imports
  - Метрики: `total_rows_processed`, `rows_skipped`, `new_sku_count`, `updated_sku_count`
  - Миграция: `db/migrations/0014_import_runs.sql`
  - PRs: #163 (Registry), #164 (Orchestrator), #165 (Polish)

- **Import Orchestrator core** (#164)
  - `scripts/import_orchestrator.py` — orchestration logic
  - `scripts/run_import_orchestrator.py` — CLI wrapper
  - `scripts/import_run_registry.py` — registry API
  - Transaction separation (R0.2): registry commits ≠ import data commits
  - Status lifecycle: pending → running → success/failed/skipped/rolled_back
  - Skip logic: если есть success для `(supplier, as_of_date, file_sha256)` → создаёт skipped attempt

- **Legacy ETL integration** (#164, #165)
  - `scripts/import_targets/run_daily_adapter.py` — adapter для `etl/run_daily`
  - Metrics normalization: `processed_rows` → `total_rows_processed`, `skipped_rows` → `rows_skipped`
  - `etl/run_daily.py` обновлён: conn parameter, as_of_date support, structured metrics return
  - Real mapping для DreemWine: `etl/mapping_template.json` (sheet="Основной", header_row=3)
  - Production validated: 262 rows processed, 298 skipped, 1.5s duration

- **Ingest envelope** (#164) — best-effort file traceability
  - `scripts/ingest_envelope.py` — файловая трассировка через SHA-256
  - Deduplication по `file_sha256` с unique index
  - `envelope_id` linkage в `import_runs` для full audit trail
  - `envelope_id` сохраняется даже в skipped attempts (фикс #165)

- **Stale run detector** (#164) — автоматическая очистка зависших импортов
  - `scripts/mark_stale_import_runs.py` — cleanup utility
  - Configurable thresholds: `--running-minutes 120 --pending-minutes 15`
  - Автоматический rollback: stuck runs → `rolled_back` status
  - PowerShell wrapper: `scripts/run_stale_detector.ps1`

- **Daily import automation** (PR-4)
  - `scripts/run_daily_import.ps1` — PowerShell wrapper для ежедневного импорта
  - Auto file discovery: находит последний файл по дате в имени (формат `YYYY_MM_DD Прайс...xlsx`)
  - Auto `as_of_date` extraction из имени файла
  - Fallback to latest file by LastWriteTime
  - venv auto-detection для .venv Python

- **Операционная документация** (PR-4)
  - `docs/dev/import_flow.md` — архитектура: компоненты, статусы, контракты, метрики
  - `docs/runbook_import.md` — operational runbook: troubleshooting, SQL queries, типовые инциденты
  - `README.md` — Import Operations section с quick start и automation
  - `QUICK_REFERENCE.md` — import commands cheat sheet
  - `INDEX.md` — навигация по документации

#### Observability & Monitoring
- **Grafana Dashboard** для мониторинга backup/DR операций (`observability/grafana/dashboards/wine-assistant-backup-dr.json`)
  - 4 панели: Backups completed (24h), Age since last backup, Restore operations (7d), Remote pruned backups (7d)
  - Auto-refresh каждые 30 секунд
  - Color thresholds для алертинга (green/yellow/red)

- **Structured JSONL logging** для всех backup/DR операций
  - `scripts/emit_event.py` — модуль для эмиссии структурированных событий (без зависимостей)
  - `logs/backup-dr/events.jsonl` — централизованный лог файл
  - 10+ типов событий: backup_local_started/completed, restore_local_started/completed, prune_*_started/completed, dr_smoke_started/completed/failed

- **Promtail integration** для сбора логов в Loki
  - Новый job `backup_dr_files` в `observability/promtail-config.yml`
  - Label extraction: level, event, service, ts_unix, deleted_count, и др.
  - Volume mount `./logs:/var/log/wine-assistant:ro` в promtail

- **Makefile targets** для управления observability stack:
  - `make obs-up` — запуск Grafana/Loki/Promtail
  - `make obs-down` — остановка observability сервисов
  - `make obs-restart` — перезапуск
  - `make obs-logs` — просмотр логов observability stack

#### Backup/DR Improvements
- **`scripts/prune_local_backups.py`** — extraction prune logic из Makefile в отдельный модуль
  - Event logging support
  - Type hints и docstrings
  - No third-party dependencies

- **Collision-proof timestamps** в именах бэкапов: `YYYYMMDD_HHMMSS_microseconds_PID`

- **Pre-restore verification** через `backup-verify` target (pg_restore --list)

- **MANAGE_PROMTAIL flag** для DR smoke tests:
  - `make dr-smoke-truncate MANAGE_PROMTAIL=1` — auto stop/start Promtail
  - Решает проблему file locking на Windows

- **Event logging** во всех backup/restore/prune операциях
  - Makefile integration через `BACKUP_EVENTS_LOG` variable
  - File stats capture (size_bytes, mtime_unix)

#### DR Smoke Test Enhancements
- Structured event logging (dr_smoke_started/completed/failed)
- Unique log files per run (timestamp + microseconds + PID)
- Optional Promtail management via `-ManagePromtail` switch
- API readiness verification (`status='ready'` not just HTTP 200)
- MinIO bucket access verification
- Fix COMPOSE_IGNORE_ORPHANS conflict
- Graceful Promtail stop/start to avoid Windows file locking

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
    - `scripts/daily_import.py` (новый файл)
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
