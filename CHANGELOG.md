# Changelog

## v0.4.3

* Release v0.4.3 — Wineries, SKU history & export (#143) (89ca4ac) by glinozem
* Align SKU API schemas with real data and refresh README (#142) (9e8d7ef) by glinozem
* Fix SKU API Schema Alignment with Live Data and History Endpoints (#141) (ea1a740) by glinozem
* Wineries Enrichment: PDF Catalog Import, New wineries Table, Products Sync, Updated API Schemas (#140) (dfbbf79) by glinozem
* Add automatic Excel image import and full image_url support in API and exports (#139) (0f459a1) by glinozem
* Add producer_site and image_url to exports; fix SKU JSON schema (#138) (fa2ede4) by glinozem
* Expose producer_site and image_url in product search and SKU APIs (#137) (de1c22d) by glinozem
* Expose wine metadata (grapes, vintage, Vivino, supplier) in API and exports (#136) (7fb4cab) by glinozem
* Document export web UI and update README (#126) (1ba0a43) by glinozem
* Implement export of search results, SKU card and price history (feature/export-69) (#125) (b114d22) by glinozem
* Add dev notes for Issue #85 (partitioning & retention job) (#124) (24ea851) by glinozem
* Merge Request: Make `0011_product_prices_partitioning` migration idempotent (#123) (08d69e9) by glinozem
* Merge Request: Partitioning `product_prices` and Retention Job (Issue #85) (#122) (f3aec71) by glinozem
* Merge Request: Windows dev setup docs and Makefile helpers (feature/quarantine-table-84) (#121) (531184a) by glinozem
* Integrate data quality gates into load_csv (Refs #83) (#120) (c222dcd) by glinozem
* Add data quality gates module and unit tests (Refs #83) (#119) (917de03) by glinozem
* Refactor ETL helpers for price import (Closes #94). (#118) (cae90f5) by glinozem
* Refactor ETL helpers in scripts/load_utils.py (Closes #94) (#117) (fde3c9a) by glinozem
* Feat/api search final price (#6) (db1209f) by glinozem
* docs (#7) (9db9212) by glinozem
* ci: bootstrap Release Drafter on default branch (#8) (d6a63d4) by glinozem
* Ci/release drafter fix local (#11) (9b0c925) by glinozem
* docs(changelog): add CHANGELOG for v0.1.7 (#26) (ac8b28e) by glinozem
* docs(changelog): add CHANGELOG for v0.1.8 (#29) (287f0ea) by glinozem
* docs(changelog): add CHANGELOG for v0.1.9 (#31) (ca5e610) by glinozem
* docs(changelog): add CHANGELOG for v0.1.10 (#34) (f5243bf) by glinozem
* docs(changelog): add CHANGELOG for v0.1.11 (#39) (32e699d) by glinozem
* docs(changelog): add CHANGELOG for v0.4.2 (#90) (7f55048) by glinozem
* Refactor/tests validation docs (#116) (82d88a7) by glinozem
* Enhance products search validation (#115) (29c133c) by glinozem
* Expose catalog search as /api/v1/products/search (#114) (9f0a9a1) by glinozem
* Feat: add dev quickstart to README (#113) (bb442cf) by glinozem
* Align ETL price history tests with API and update README (#112) (6bee2e5) by glinozem
* Fix migrator DB wiring and document DB setup in README (#111) (361d7b7) by glinozem
* Refine price history ETL tests and sync README/.env.example (#110) (4772c82) by glinozem
* test: add integration test for price import ETL (#109) (dd01652) by glinozem
* docs: document local DB and tests workflow (#108) (038ff8b) by glinozem
* ci: remove legacy tests workflow (#107) (92d1b45) by glinozem
* feat(api): hardening app.py + prod server + rate limits & tests (16c6d57) by glinozem
* db(migrations): fix schema_migrations_view (correct quotes; add MSK column) (#105) (ece4528) by glinozem
* db(migrations): fix schema_migrations_view (correct quotes; add MSK column) (#104) (fdc9681) by glinozem
* docs/ci-db: README refresh + CI DB provisioning + migrations (#100) (bdbd884) by glinozem
* ci: run Postgres on 15432 in CI + load schemas (pgcrypto, products, inventory) (44d5ec7) by glinozem
* chore(etl): finalize helper refactoring and tests (#91) (b80270a) by glinozem
* feat(etl): implement automated daily import scheduler (#93) (729b8d5) by glinozem
* test: Add Add unit+integration tests for load_csv + idempotency (Issue #91) (#92) (dc60e95) by glinozem
