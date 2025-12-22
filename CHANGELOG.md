# Changelog

## [Unreleased]

### Added

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
- `scripts/cleanup_test_data.py` — утилита очистки тестовых/интеграционных данных в Postgres (dry-run по умолчанию, `--apply` для выполнения).
- UI `/ui`: бесконечная прокрутка и корректная загрузка всех позиций поверх пагинации (`limit/offset`), а не только первой страницы.
- Документация: обновлены команды PowerShell для вызовов API (`Invoke-RestMethod` / `curl.exe`), добавлены примеры очистки тестовых данных.
- **`project-structure.txt`** — обновлена структура с учётом observability файлов

### Fixed
- Тесты: скорректирован unit-тест, который проверяет приоритет `df.attrs['prefer_discount_cell']` над `PREFER_S5` (в `scripts/load_utils.py` логика уже корректна).
- DR smoke test: file locking issues на Windows при использовании Promtail

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
*  feat(testing): Setup pytest infrastructure (Issue #57) (#70) (d0a646c) by glinozem
* Feature/structured logging (#55) (73c8480) by glinozem
* docs(changelog): add CHANGELOG for v0.4.1 (#54) (d26e421) by glinozem
