.PHONY: help dev-up dev-down dev-logs db-shell db-migrate         test test-unit test-int test-int-noslow lint fmt         check test-all test-db db-reset load-price show-quarantine

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

dev-up:
	docker compose up -d db api

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f api db

db-shell:
	docker compose exec db psql -U postgres -d wine_db

db-migrate:
	bash db/migrate.sh

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
	docker compose down -v
	docker compose up -d

load-price:
	python -m scripts.load_csv --excel "$(EXCEL_PATH)"

show-quarantine:
	psql "host=$(DB_HOST) port=$(DB_PORT) user=$(PGUSER) password=$(PGPASSWORD) dbname=$(PGDATABASE)" -c "SELECT id, envelope_id, code, dq_errors, created_at FROM price_list_quarantine ORDER BY created_at DESC LIMIT 50;"
