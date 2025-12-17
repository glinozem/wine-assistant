# Changelog

## v0.4.2

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


## [Unreleased]

### Added
- `scripts/cleanup_test_data.py` — утилита очистки тестовых/интеграционных данных в Postgres (dry-run по умолчанию, `--apply` для выполнения).

### Changed
- UI `/ui`: бесконечная прокрутка и корректная загрузка всех позиций поверх пагинации (`limit/offset`), а не только первой страницы.
- Документация: обновлены команды PowerShell для вызовов API (`Invoke-RestMethod` / `curl.exe`), добавлены примеры очистки тестовых данных.

### Fixed
- Тесты: скорректирован unit-тест, который проверяет приоритет `df.attrs['prefer_discount_cell']` над `PREFER_S5` (в `scripts/load_utils.py` логика уже корректна).
