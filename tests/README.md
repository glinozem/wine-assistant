# Тесты в проекте `wine-assistant`

Этот файл описывает структуру тестов, используемые маркеры и то, как их запускать локально и в CI.

## Структура каталогов

- `tests/unit/` — юнит-тесты (логика без реальной БД и внешних сервисов):
  - `test_load_utils.py`, `test_load_csv.py` и др.
  - `test_schemas.py` — тесты Pydantic-схем (`api/schemas.py`).
  - `test_validation.py` — тесты хелпера валидации (`api/validation.py`).
  - `test_health.py`, `test_date_extraction.py`, `test_idempotency.py` и др.

- `tests/integration/` — интеграционные тесты (нужна реальная БД и/или HTTP API):
  - `test_price_import_etl.py` — end-to-end ETL загрузки прайса в БД + сверка с API.
  - `test_api_products_search_happy.py` — интеграционные тесты поиска по каталогу.
  - `api_test_utils.py` — общие хелперы для интеграционных тестов (вызовы API и поиска).
  - `conftest.py` — настройка окружения для интеграционных тестов (переменные PG* и отключение rate limit).

- Файлы `tests/test_*.py` в корне:
  - `test_api_products_happy.py`, `test_api_products_validation.py`, `test_api_search_validation.py` и др. — API-тесты поверх Flask-приложения.
  - `test_api_limits_and_security.py`, `test_api_health.py` и др.

## Маркеры pytest

Маркеры объявлены в `pytest.ini`:

- `@pytest.mark.unit` — юнит-тесты.
- `@pytest.mark.integration` — интеграционные тесты, требующие реальной БД / внешних сервисов.
- `@pytest.mark.e2e` — end-to-end сценарии (напр., полный цикл ETL).
- `@pytest.mark.slow` — медленные тесты.
- `@pytest.mark.smoke` — базовые smoke-тесты (можно запускать как быстрый sanity-check).
- `@pytest.mark.requires_real_data` — тесты, завязанные на реальные данные/датасет.
- `@pytest.mark.monitoring` — мониторинговые тесты по реальным SKU / данным (обычно не запускаются в обычном CI-пайплайне).

Важно: часть интеграционных тестов использует флаг `RUN_DB_TESTS`, чтобы не падать, если БД не поднята.

## Переменные окружения

### Для БД

Используются следующие переменные (как в `ci.yml`, так и локально):

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

В интеграционных тестах (`tests/integration/conftest.py`) по умолчанию выставляются значения для локальной БД из `docker-compose`:

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGPASSWORD`

### Флаг интеграционных тестов

- `RUN_DB_TESTS`:
  - `"1"` — включить тесты, требующие реальной БД.
  - Любое другое значение / отсутствие — такие тесты будут пропущены через `pytest.mark.skipif`.

### Для HTTP API

Интеграционные тесты, которые ходят в HTTP API (через `requests`), используют:

- `API_URL` — базовый URL API (по умолчанию `http://localhost:18000`).
- `API_KEY` — ключ для защищённых эндпоинтов.
- `API_BASE_URL` — может переопределять `API_URL` при вызовах в тестах.

## Как запускать тесты локально

### Все тесты (юнит + интеграционные, если включены)

```bash
pytest -q
```

> Если `RUN_DB_TESTS` не равен `"1"`, интеграционные тесты, завязанные на БД, будут пропущены.

### Только юнит-тесты

```bash
pytest -q -m "not integration and not monitoring"
```

### Интеграционные тесты (с поднятой БД)

1. Поднять PostgreSQL (например, через `docker compose up -d db`).
2. Установить переменные окружения для подключения (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
3. Включить флаг:

```bash
export RUN_DB_TESTS=1
pytest -m "integration and not monitoring" -v
```

### Мониторинговые тесты по реальным SKU

Тесты с `@pytest.mark.monitoring` завязаны на реальные SKU / данные и не запускаются в обычном CI.

Локальный запуск (при доступной БД и API):

```bash
export RUN_DB_TESTS=1
pytest -m "monitoring" -v
```

## CI (GitHub Actions)

В `ci.yml` в job `tests` используется:

```bash
pytest -q -m "not monitoring"
```

Это означает, что в CI:

- выполняются все тесты, **кроме** помеченных `@pytest.mark.monitoring`;
- интеграционные тесты включаются, если выставлен `RUN_DB_TESTS=1` и поднята БД (через `docker compose`).

## Линтер

В проекте настроен `ruff`:

- Локальный запуск:

```bash
ruff check .
```

На данный момент `ruff` **не** включён в GitHub Actions, но код и тесты приведены к его требованиям, поэтому локально команда `ruff check .` должна проходить без ошибок.
