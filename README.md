# Wine Assistant — API & ETL для прайс-листа вина

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Semgrep](https://github.com/glinozem/wine-assistant/actions/workflows/semgrep.yml/badge.svg)](../../actions/workflows/semgrep.yml)
[![Secrets](https://github.com/glinozem/wine-assistant/actions/workflows/secrets.yml/badge.svg)](../../actions/workflows/secrets.yml)

Небольшой учебный проект: REST-API для работы с прайс-листом вина + ETL-скрипт для загрузки данных из Excel/CSV в PostgreSQL.
Проект используется как «песочница» для практики по:

* проектированию API и документации (Flask + Swagger)
* работе с PostgreSQL, миграциями и Docker Compose
* нагрузочному и интеграционному тестированию (pytest, requests)
* CI/CD (GitHub Actions, Semgrep, pip-audit, secret-scan)
* постепенному «оживлению» продукта через Roadmap и спринты.

**Текущий статус:** учебный pet-project, активно дорабатывается. См. подробный Roadmap: [`docs/ROADMAP_v3_RU.md`](docs/ROADMAP_v3_RU.md).

---

## TL;DR — как быстро запустить

### Вариант A. Всё через Docker Compose (рекомендовано)

Требуется: Docker + Docker Compose.

```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# 1. Создаём .env на основе примера
cp .env.example .env
# при необходимости поправьте пароли, порты и API_KEY

# 2. Поднимаем всё окружение
docker compose up -d --build

# 3. Проверяем API
curl http://localhost:18000/health
curl http://localhost:18000/ready
```

* API слушает на `http://localhost:18000`
* Swagger UI доступен по адресу: `http://localhost:18000/docs`

### Вариант B. Локальный запуск без Docker

Требуется: установленный PostgreSQL и Python 3.11+.

```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

python -m venv .venv
# Windows:
# .venv\Scripts\activate
# Linux / macOS:
# source .venv/bin/activate

pip install -r requirements.txt

# Настраиваем окружение для подключения к локальной БД
cp .env.example .env
# правим .env под вашу PostgreSQL (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD)

# Запуск дев-сервера Flask
FLASK_ENV=development FLASK_APP=api.app flask run
# API:    http://127.0.0.1:5000
# Swagger http://127.0.0.1:5000/docs
```

В production-режиме в контейнере используется `gunicorn` с WSGI-обёрткой.

---

## Архитектура и основные компоненты

Проект условно делится на три слоя:

1. **API (Flask-приложение)**
   * эндпоинты для работы с товарами (SKU), ценами и остатками
   * формат запросов/ответов — JSON
   * документация — Swagger UI на `/docs`
   * авторизация — через API-ключ (заголовок `X-API-Key`)

2. **ETL-скрипты**
   * загрузка прайс-листа из Excel/CSV в промежуточные таблицы
   * нормализация и сохранение цен/остатков в основные таблицы
   * примеры скриптов лежат в `scripts/` (главный — `scripts/load_csv.py`)

3. **База данных (PostgreSQL)**
   * схемы и таблицы описаны через миграции (Alembic)
   * отдельные таблицы для товаров, цен, истории остатков и т.п.
   * пример структуры можно посмотреть в миграциях в `db/migrations/versions/`

---

## Конфигурация базы данных

Подключение к PostgreSQL настраивается через переменные окружения.

**Для приложения и ETL внутри Docker-сети:**

```env
DB_HOST=db
DB_PORT=5432
DB_NAME=wine_db
DB_USER=postgres
DB_PASSWORD=postgres
```

**Для утилит psql / локальных тестов с хоста:**

```env
PGHOST=localhost
PGPORT=15432
PGUSER=postgres
PGPASSWORD=postgres
PGDATABASE=wine_db
```

При запуске через Docker Compose БД пробрасывается на хост как `localhost:15432`.
Скрипты используют вспомогательную функцию `scripts.load_utils.get_conn()`, которая:
* собирает конфиг подключения из `DB_*` и/или `PG*`,
* добавляет `connect_timeout`,
* даёт понятные сообщения об ошибках при недоступности БД.

---

## Аутентификация и API_KEY

Часть эндпоинтов (например, SKU и price-history) защищены простым API-ключом.

1. Сгенерируйте ключ и пропишите его в `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```env
API_KEY=your-secret-api-key-minimum-32-chars
```

2. Передавайте ключ в заголовке `X-API-Key`:

```bash
curl   -H "X-API-Key: $API_KEY"   "http://localhost:18000/api/v1/sku/DUMMY_CODE/price-history"
```

В интеграционных тестах тот же ключ берётся из переменной окружения `API_KEY`.

---

## Загрузка прайс-листа в БД

Главный учебный сценарий: есть поставщик, который присылает прайс в виде Excel или CSV.
Нужно:

1. загрузить прайс в промежуточную таблицу,
2. нормализовать данные,
3. сохранить актуальные цены и историю изменений.

Для этого используется скрипт `scripts/load_csv.py`.

### Пример запуска ETL локально (с Docker-БД)

```bash
# Активируем виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Выставляем переменные подключения к БД (через проброшенный порт)
export DB_HOST=127.0.0.1
export DB_PORT=15432
export DB_NAME=wine_db
export DB_USER=postgres
export DB_PASSWORD=postgres

# Запускаем загрузку CSV
python scripts/load_csv.py --csv path/to/pricelist.csv
```

Формат CSV-файла описан в docstring’ах `load_csv.py` и в тестах в `tests/unit/test_load_csv.py`.

---

## Тестирование

Вся логика покрыта pytest’ом: как API, так и ETL-часть.

### Локальный запуск тестов

```bash
# без интеграционных тестов с реальной БД
pytest -q

# только быстрые юнит-тесты
pytest tests/unit -q
```

Интеграционные тесты, которые работают с PostgreSQL (и иногда с живым API),
помечены `@pytest.mark.integration` и по умолчанию **пропускаются**.

Чтобы их включить, поднимите локальную БД через Docker Compose и выставьте переменные окружения:

```bash
# включаем интеграционные тесты
export RUN_DB_TESTS=1

# хост и порт БД для приложений/скриптов (проброшенный порт Docker)
export DB_HOST=localhost
export DB_PORT=15432    # см. docker-compose.yml

# те же настройки для psql и pg_* утилит
export PGHOST=localhost
export PGPORT=15432
export PGUSER=postgres
export PGPASSWORD=postgres
export PGDATABASE=wine_db

# API для интеграционных тестов
export API_URL=http://localhost:18000
export API_BASE_URL=http://localhost:18000
export API_KEY=your-secret-api-key-minimum-32-chars

pytest -m "integration" -vv
```

Интеграционные сценарии включают в себя:

* базовый импорт прайс-листа (smoke)
* проверку, что данные реально попадают в таблицы БД
* проверку идемпотентности (повторный импорт не ломает данные)
* сопоставление данных API `/price-history` с тем, что лежит в таблицах БД.

---

## CI и качество кода

В проекте настроены несколько GitHub Actions:

1. **CI (pytest + линтеры)**
   * прогоняет тесты
   * проверяет код на базовые ошибки

2. **Semgrep**
   * статический анализ кода на типовые ошибки и уязвимости

3. **Secrets scan**
   * проверяет, что в репозиторий не попали реальные токены/пароли

4. **pip-audit**
   * анализирует зависимости на наличие известных уязвимостей

Запустить базовые проверки локально:

```bash
pytest -q
pip-audit -r requirements.txt --strict
```

---

## Roadmap и ближайшие цели

Подробная дорожная карта лежит в `docs/ROADMAP_v3_RU.md`.

Сюда вынесены только укрупнённые задачи:

1. **Укрепление API и инфраструктуры**
   * Доведение health-чеков до production-варианта
   * Ограничения по rate-limit’ам (Flask-Limiter)
   * Ещё тесты на негативные сценарии и валидацию входных данных

2. **Расширение ETL**
   * Поддержка нескольких форматов прайс-листа
   * Улучшенный audit-лог и отчётность по загрузкам

3. **Подготовка к демо / курсовому проекту**
   * Красивый Swagger
   * Скрипты для демонстрационных данных
   * Документация по развёртыванию «в один клик» (Docker / Makefile).

---

## Как контрибьютить (для будущего «я»)

1. Находишь задачу в Roadmap или заводишь Issue.
2. Создаёшь ветку от `master`:

   ```bash
   git checkout -b feature/my-task
   ```

3. Пишешь код + тесты:

   * не забываешь про юнит-тесты
   * если меняешь схему БД — добавляешь миграцию
   * прогоняешь локально:
     ```bash
     pytest -q
     pip-audit -r requirements.txt --strict
     ```

4. Открываешь PR, в описании:
   * кратко формулируешь задачу (ссылка на Issue / пункт Roadmap),
   * описываешь, что поменял,
   * при необходимости добавляешь скриншоты / примеры запросов.

---

## Лицензия

Учебный проект, лицензия: **MIT** (см. файл `LICENSE`).

Проект можно использовать как основу для собственных pet-проектов, экспериментов с CI/CD и отработки навыков backend-разработки.
