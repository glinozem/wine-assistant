.PHONY: help dev-up dev-down dev-logs db-shell db-migrate \
        test test-unit test-int test-int-noslow lint fmt

# Значения по умолчанию для окружения, можно переопределить при вызове:
# например: make test-int DB_HOST=127.0.0.1
export DB_HOST ?= localhost
export DB_PORT ?= 15432
export API_URL ?= http://localhost:18000
export API_BASE_URL ?= $(API_URL)
export RUN_DB_TESTS ?=

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
	@echo "  make lint            - ruff check ."
	@echo "  make fmt             - auto-fix ruff (если включены правила форматирования)"

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
	RUN_DB_TESTS=1 pytest -m "integration" -vv

test-int-noslow:
	RUN_DB_TESTS=1 pytest -m "integration and not slow" -vv

lint:
	ruff check .

fmt:
	ruff check . --fix
