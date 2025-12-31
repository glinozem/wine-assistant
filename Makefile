.PHONY: help dev-up dev-down dev-logs db-shell db-migrate         test test-unit test-int test-int-noslow lint fmt         check test-all test-db db-reset load-price show-quarantine
.PHONY: sync-inventory-history sync-inventory-history-dry-run
.PHONY: backfill-current-prices backfill-current-prices-dry-run
.PHONY: bundle bundle-static bundle-full

# Значения по умолчанию для окружения, можно переопределить при вызове:
# например: make test-int DB_HOST=127.0.0.1
export DB_HOST ?= localhost
export DB_PORT ?= 15432
export API_URL ?= http://localhost:18000
export API_BASE_URL ?= $(API_URL)
export RUN_DB_TESTS ?=
# Кросс-платформенная установка переменной окружения для тестов с БД
ifeq ($(OS),Windows_NT)
  SET_DBTEST_ENV = set RUN_DB_TESTS=1 &&
else
  SET_DBTEST_ENV = RUN_DB_TESTS=1
endif

DOCKER_COMPOSE ?= docker compose
OBS_DOCKER_COMPOSE ?= $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.storage.yml -f docker-compose.observability.yml

# Python launcher (override if needed): make PY=python3 ...
PY ?= python

# --- Analysis bundle (архив для ревью/диагностики) ---
BUNDLE_OUT_DIR ?= ./_bundles

ifeq ($(OS),Windows_NT)
  POWERSHELL ?= powershell
  POWERSHELL_ARGS ?= -NoProfile -ExecutionPolicy Bypass -File
else
  POWERSHELL ?= pwsh
  POWERSHELL_ARGS ?= -NoProfile -File
endif


# Путь к прайс-листу по умолчанию (можно переопределять при вызове)
EXCEL_PATH ?= ./data/price-list.xlsx

# Значения по умолчанию для psql при работе с БД
export PGUSER ?= postgres
export PGPASSWORD ?= postgres
export PGDATABASE ?= wine_db

help:
	@echo "Доступные команды:"
	@echo "  make dev-up          - поднять db + api через docker compose"
	@echo "  make dev-down        - остановить контейнеры"
	@echo "  make dev-logs        - логи api и db"
	@echo "  make db-shell        - psql в контейнер db"
	@echo "  make db-migrate      - применить миграции (если есть скрипт db/migrate.sh)"
	@echo "  make test            - все тесты (без фильтров)"
	@echo "  make test-unit       - только unit-тесты"
	@echo "  make test-int        - интеграционные тесты (RUN_DB_TESTS=1)"
	@echo "  make test-int-noslow - интеграционные без медленных (slow)"
	@echo "  make test-db         - алиас для интеграционных тестов с БД"
	@echo "  make lint            - ruff check ."
	@echo "  make fmt             - auto-fix ruff (если включены правила форматирования)"
	@echo "  make check           - линтер + все тесты"
	@echo "  make load-price      - загрузить прайс-лист в БД (scripts/load_csv)"
	@echo "  make show-quarantine - показать последние строки из price_list_quarantine"
	@echo "  make db-reset        - пересоздать БД (docker compose down -v && up db+migrator)"
	@echo "  make sync-inventory-history        - синхронизировать текущие остатки (inventory) в историю (inventory_history)"
	@echo "  make sync-inventory-history-dry-run - показать, сколько записей будет добавлено в inventory_history (без изменений БД)"
	@echo "  make backfill-current-prices        - привести цены к контракту и дозаполнить current price rows в product_prices (apply)"
	@echo "  make backfill-current-prices-dry-run - показать, что будет исправлено/вставлено (dry-run)"
	@echo "  make bundle           - собрать analysis bundle (без static/)"
	@echo "  make bundle-static    - собрать analysis bundle (включая static/)"
	@echo "  make bundle-full      - bundle + static/ + pip freeze"

dev-up:
	$(DOCKER_COMPOSE) up -d db api

dev-down:
	$(DOCKER_COMPOSE) down

dev-logs:
	$(DOCKER_COMPOSE) logs -f api db

# Observability stack (Grafana/Loki/Promtail) - start/stop without orphan warnings
.PHONY: obs-up obs-down obs-restart obs-logs
obs-up:
	$(OBS_DOCKER_COMPOSE) up -d grafana loki promtail

obs-down:
	$(OBS_DOCKER_COMPOSE) stop grafana loki promtail

obs-restart:
	$(OBS_DOCKER_COMPOSE) restart grafana loki promtail

obs-logs:
	$(OBS_DOCKER_COMPOSE) logs -f --tail=200 grafana loki promtail

db-shell:
	$(DOCKER_COMPOSE) exec db psql -U postgres -d wine_db

db-migrate:
ifeq ($(OS),Windows_NT)
	$(POWERSHELL) $(POWERSHELL_ARGS) db/migrate.ps1
else
	bash db/migrate.sh
endif

test:
	pytest -q

test-unit:
	pytest tests/unit -q

test-int:
	$(SET_DBTEST_ENV) pytest -m "integration" -vv

test-int-noslow:
	$(SET_DBTEST_ENV) pytest -m "integration and not slow" -vv

lint:
	ruff check .

fmt:
	ruff check . --fix
# Сводные цели для тестов и работы с данными прайс-листа

check: lint test
	@echo "✅ Линтер и тесты прошли"

test-all: test

test-db: test-int

db-reset:
	@echo "Пересоздаём docker-compose окружение с БД..."
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) up -d

load-price:
	$(PY) -m scripts.load_csv --excel "$(EXCEL_PATH)"

show-quarantine:
	psql "host=$(DB_HOST) port=$(DB_PORT) user=$(PGUSER) password=$(PGPASSWORD) dbname=$(PGDATABASE)" -c "SELECT id, envelope_id, code, dq_errors, created_at FROM price_list_quarantine ORDER BY created_at DESC LIMIT 50;"

sync-inventory-history:
	$(DOCKER_COMPOSE) exec api python -m scripts.sync_inventory_history $(if $(AS_OF),--as-of "$(AS_OF)",)

backfill-current-prices-dry-run:
	$(DOCKER_COMPOSE) exec api python -m scripts.backfill_current_prices --dry-run

backfill-current-prices:
	$(DOCKER_COMPOSE) exec api python -m scripts.backfill_current_prices --apply

sync-inventory-history-dry-run:
	$(DOCKER_COMPOSE) exec api python -m scripts.sync_inventory_history $(if $(AS_OF),--as-of "$(AS_OF)",) --dry-run

bundle:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/bundle.ps1 -OutDir "$(BUNDLE_OUT_DIR)"

bundle-static:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/bundle.ps1 -OutDir "$(BUNDLE_OUT_DIR)" -IncludeStatic

bundle-full:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/bundle.ps1 -OutDir "$(BUNDLE_OUT_DIR)" -IncludeStatic -IncludePipFreeze

db-backup:
	$(DOCKER_COMPOSE) --profile backup run --rm backup backup

db-restore-test:
	$(DOCKER_COMPOSE) --profile backup run --rm backup restore-test

db-backup-dry-run-delete:
	$(DOCKER_COMPOSE) --profile backup run --rm backup bash -lc 'rclone delete "$${RCLONE_REMOTE}:$${S3_BUCKET}/$${S3_PREFIX}/" --min-age "$${RETENTION_REMOTE_DAYS}d" --dry-run'

# -----------------------------
# Backups: local + "remote" (MinIO)
# -----------------------------

DB_NAME ?= wine_db
DB_USER ?= postgres
DB_CONTAINER ?= wine-assistant-db

BACKUPS_DIR ?= backups
RESTORE_DIR ?= restore_tmp
BACKUP_KEEP ?= 10


# JSONL log file for backup/DR events (used by Promtail/Loki in observability stack)
BACKUP_EVENTS_LOG ?= logs/backup-dr/events.jsonl

MINIO_ROOT_USER ?= minioadmin
MINIO_ROOT_PASSWORD ?= minioadmin123
MINIO_BUCKET ?= wine-backups
MINIO_PREFIX ?= postgres
MINIO_ENDPOINT_INTERNAL ?= http://minio:9000

# Важно: timestamp генерим питоном (кроссплатформенно)
TS := $(shell $(PY) -c "import datetime as d, os; print(d.datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + str(os.getpid()))")
BACKUP_FILE := $(DB_NAME)_$(TS).dump
LATEST_BACKUP := $(shell $(PY) -c "import glob; f=sorted(glob.glob('$(BACKUPS_DIR)/$(DB_NAME)_*.dump')); print(f[-1] if f else '')")

DC ?= $(DOCKER_COMPOSE)
DC_STORAGE = $(DC) -f docker-compose.yml -f docker-compose.storage.yml

.PHONY: storage-up storage-down backups-list-local backups-list-remote backup-local backup-upload backup \
        backup-download-remote restore-local restore-remote
.PHONY: backup-verify
.PHONY: prune-local
.PHONY: prune-remote

storage-up:
	$(DC_STORAGE) up -d minio minio-init

storage-down:
	$(DC_STORAGE) down -v --remove-orphans

backups-list-local:
	$(PY) -c "import glob; [print(x) for x in sorted(glob.glob('$(BACKUPS_DIR)/*.dump'))]"

backup-local:
	$(PY) -c "import os; os.makedirs('$(BACKUPS_DIR)', exist_ok=True)"
	$(PY) -m scripts.emit_event --log-file "$(BACKUP_EVENTS_LOG)" --event backup_local_started --service backup --field file=$(BACKUP_FILE)
	$(DC) exec -T db bash -lc "pg_dump -U $(DB_USER) -d $(DB_NAME) -Fc -f /backups/$(BACKUP_FILE)"
	$(PY) -m scripts.emit_event --log-file "$(BACKUP_EVENTS_LOG)" --event backup_local_completed --service backup --field file=$(BACKUP_FILE) --stat-file "$(BACKUPS_DIR)/$(BACKUP_FILE)"
	@echo "OK: local backup -> $(BACKUPS_DIR)/$(BACKUP_FILE)"

backup-upload: storage-up
	$(DC_STORAGE) --profile tools run --rm mc "mc alias set local $(MINIO_ENDPOINT_INTERNAL) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD) && \
	  mc cp /backups/$(BACKUP_FILE) local/$(MINIO_BUCKET)/$(MINIO_PREFIX)/$(BACKUP_FILE) && \
	  mc ls local/$(MINIO_BUCKET)/$(MINIO_PREFIX)/"

backup: backup-local backup-verify backup-upload prune-local prune-remote
backups-list-remote: storage-up
	$(DC_STORAGE) --profile tools run --rm mc "mc alias set local $(MINIO_ENDPOINT_INTERNAL) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD) && \
	  mc ls local/$(MINIO_BUCKET)/$(MINIO_PREFIX)/"

# Использование: make backup-download-remote FILE=wine_db_YYYYMMDD_HHMMSS.dump
backup-download-remote: storage-up
	$(PY) -c "import os; os.makedirs('$(RESTORE_DIR)', exist_ok=True)"
	$(DC_STORAGE) --profile tools run --rm mc "mc alias set local $(MINIO_ENDPOINT_INTERNAL) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD) && \
	  mc cp local/$(MINIO_BUCKET)/$(MINIO_PREFIX)/$(FILE) /restore/$(FILE) && \
	  ls -lah /restore/$(FILE)"

# restore из локального файла:
# - по умолчанию возьмёт самый свежий backups/wine_db_*.dump
# - либо: make restore-local FILE=backups/wine_db_....dump
restore-local:
	$(PY) -c "import sys; f='$(FILE)' if '$(FILE)' else '$(LATEST_BACKUP)'; print('Using:', f) if f else sys.exit('No backup found. Set FILE=...')"
	$(PY) -m scripts.emit_event --log-file "$(BACKUP_EVENTS_LOG)" --event restore_local_started --service backup --field file=$(if $(FILE),$(FILE),$(LATEST_BACKUP))
	$(MAKE) backup-verify FILE=$(if $(FILE),$(FILE),$(LATEST_BACKUP))
	$(DC) stop api
	$(DC) exec -T db bash -lc "dropdb -U $(DB_USER) --if-exists $(DB_NAME) && createdb -U $(DB_USER) $(DB_NAME)"
	docker cp $(if $(FILE),$(FILE),$(LATEST_BACKUP)) $(DB_CONTAINER):/tmp/restore.dump
	$(DC) exec -T db bash -lc "pg_restore -U $(DB_USER) -d $(DB_NAME) --clean --if-exists /tmp/restore.dump"
	$(DC) start api
	$(PY) -m scripts.emit_event --log-file "$(BACKUP_EVENTS_LOG)" --event restore_local_completed --service backup --field file=$(if $(FILE),$(FILE),$(LATEST_BACKUP))
	@echo "OK: restore completed"

# restore из MinIO: make restore-remote FILE=wine_db_....dump
restore-remote: backup-download-remote
	$(MAKE) restore-local FILE=$(RESTORE_DIR)/$(FILE)

# Download latest remote backup from MinIO into restore_tmp/remote_latest.dump
.PHONY: backup-download-remote-latest restore-remote-latest

backup-download-remote-latest: storage-up
	$(PY) -m scripts.minio_backups download-latest --emit-json --log-file "$(BACKUP_EVENTS_LOG)" --bucket $(MINIO_BUCKET) --prefix $(MINIO_PREFIX) --endpoint $(MINIO_ENDPOINT_INTERNAL) --user $(MINIO_ROOT_USER) --password $(MINIO_ROOT_PASSWORD) --restore-dir $(RESTORE_DIR) --dest-name remote_latest.dump

# Restore DB from latest remote backup (remote_latest.dump)
restore-remote-latest: backup-download-remote-latest
	$(MAKE) restore-local FILE=$(RESTORE_DIR)/remote_latest.dump

backup-verify:
	@echo "Verifying dump using pg_restore -l (inside db container)..."
	@echo "  file: $(if $(FILE),$(FILE),$(BACKUPS_DIR)/$(BACKUP_FILE))"
	@docker cp "$(if $(FILE),$(FILE),$(BACKUPS_DIR)/$(BACKUP_FILE))" $(DB_CONTAINER):/tmp/verify.dump
	@$(DC) exec -T db bash -lc "pg_restore -l /tmp/verify.dump > /dev/null"
	@$(DC) exec -T db bash -lc "rm -f /tmp/verify.dump"
	@echo "OK: backup verified"

prune-local:
	@echo "Pruning local backups: keep last $(BACKUP_KEEP)"
	$(PY) -m scripts.prune_local_backups --backups-dir "$(BACKUPS_DIR)" --db-name "$(DB_NAME)" --keep "$(BACKUP_KEEP)" --log-file "$(BACKUP_EVENTS_LOG)"

prune-remote: storage-up
	@echo "Pruning remote backups in MinIO: keep last $(BACKUP_KEEP)"
	$(PY) -m scripts.minio_backups prune --keep $(BACKUP_KEEP) --emit-json --log-file "$(BACKUP_EVENTS_LOG)" --bucket $(MINIO_BUCKET) --prefix $(MINIO_PREFIX) --endpoint $(MINIO_ENDPOINT_INTERNAL) --user $(MINIO_ROOT_USER) --password $(MINIO_ROOT_PASSWORD)

# --- DR / Backups helpers -------------------------------------------------
# Windows-friendly PowerShell invocation from make.
# DR_BACKUP_KEEP can be overridden per command:
#   make dr-smoke-truncate DR_BACKUP_KEEP=2

DR_BACKUP_KEEP ?= 2
MANAGE_PROMTAIL ?= 0

.PHONY: dr-smoke-truncate dr-smoke-dropvolume

dr-smoke-truncate:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/dr_smoke.ps1 -Mode truncate -BackupKeep $(DR_BACKUP_KEEP) $(if $(filter 1,$(MANAGE_PROMTAIL)),-ManagePromtail)

dr-smoke-dropvolume:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/dr_smoke.ps1 -Mode dropvolume -BackupKeep $(DR_BACKUP_KEEP) $(if $(filter 1,$(MANAGE_PROMTAIL)),-ManagePromtail)

.PHONY: smoke-e2e

SMOKE_SUPPLIER ?= dreemwine
SMOKE_BASE_URL ?= http://localhost:18000
SMOKE_FRESH ?= 0
SMOKE_BUILD ?= 0
SMOKE_STALE_MODE ?= whatif
SMOKE_API_SMOKE ?= 0

smoke-e2e:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/smoke_e2e.ps1 -Supplier "$(SMOKE_SUPPLIER)" -BaseUrl "$(SMOKE_BASE_URL)" -StaleDetectorMode "$(SMOKE_STALE_MODE)" $(if $(filter 1,$(SMOKE_FRESH)),-Fresh) $(if $(filter 1,$(SMOKE_BUILD)),-Build) $(if $(filter 1,$(SMOKE_API_SMOKE)),-RunApiSmoke)


# --- Daily incremental import ----------------------------------------------

.PHONY: daily-import daily-import-files daily-import-ps1

# Auto-inbox: take ONLY the newest .xlsx from data/inbox and process it.
daily-import:
	$(PY) -m scripts.daily_import --inbox "data/inbox"

# Explicit files list:
#   make daily-import-files FILES="data/inbox/a.xlsx data/inbox/b.xlsx"
daily-import-files:
	$(PY) -m scripts.daily_import --files $(FILES)

# Windows PowerShell wrapper (alternative):
#   make daily-import-ps1
#   make daily-import-ps1 FILES="data\\inbox\\a.xlsx"  (space-separated)
daily-import-ps1:
	$(POWERSHELL) $(POWERSHELL_ARGS) scripts/run_daily_import.ps1 $(if $(FILES),-Files $(FILES))
