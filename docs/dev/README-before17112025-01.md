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
# при необходимости поправьте пароли/порты

# 2. Поднимаем всё окружение
docker compose up -d --build

# 3. Проверяем API
curl http://localhost:8080/api/v1/health/live
curl http://localhost:8080/api/v1/health/ready
```

* API слушает на `http://localhost:8080`
* Swagger-UI (Flasgger) доступен по адресу: `http://localhost:8080/apidocs/`
* PostgreSQL разворачивается в контейнере `wine-assistant-db`
* Миграции применяются скриптом `db/migrate.sh` во время CI и локально.

---

### Вариант B. Локальный запуск API (без Docker)

Требуется: Python 3.11+ и локальная PostgreSQL.

```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Настраиваем окружение для подключения к БД
cp .env.example .env
# правим .env под вашу локальную PostgreSQL

# Запуск дев-сервера Flask
FLASK_ENV=development flask --app app.py run
# API: http://127.0.0.1:5000
# Swagger: http://127.0.0.1:5000/apidocs/
```

Для production-режима в контейнере используется `gunicorn` c WSGI-обёрткой `wsgi.py`.

---

## Архитектура и основные компоненты

Проект условно состоит из трёх частей:

1. **REST-API (`app.py`, `wsgi.py`)**
   * Flask + Flasgger
   * Версионирование: `/api/v1/...`
   * Health-эндпоинты:
     * `GET /api/v1/health/live`
     * `GET /api/v1/health/ready`
   * Работа с товарами:
     * `GET /api/v1/products` — список товаров с пагинацией и сортировкой
     * `GET /api/v1/products/{code}` — карточка товара по коду
     * `GET /api/v1/products/search` — поиск по коду/названию/стране и т.п.

2. **ETL-скрипты для прайс-листа (`scripts/`)**
   * `scripts/load_csv.py` — основная утилита для загрузки CSV/Excel в БД
   * `scripts/load_utils.py` — вспомогательные функции:
     * чтение CSV/Excel
     * нормализация колонок и цен
     * upsert в таблицы PostgreSQL
     * работа с «конвертами» загрузки (audit трейл)
   * `scripts/date_extraction.py` — извлечение даты прайс-листа из имени/содержимого файла

3. **Инфраструктура**
   * `docker-compose.yml` — API + PostgreSQL + Adminer
   * `db/` — SQL-скрипты и миграции
     * `db/migrate.sh` — универсальный скрипт для применения миграций
   * `.github/workflows/` — CI-workflow’ы

---

## Конфигурация базы данных

Подключение к PostgreSQL настраивается через переменные окружения:

**Для API и ETL:**

```bash
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=wine_db
DB_USER=postgres
DB_PASSWORD=postgres
```

**Для утилит psql / скриптов миграций (PG-переменные):**

```bash
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=postgres
PGDATABASE=wine_db
```

В Docker Compose значения берутся из `.env`.
В коде всё читается через `scripts.load_utils.get_conn()`, который:

* собирает конфиг подключения из `DB_*` и/или `PG*`
* выставляет `connect_timeout`
* даёт понятные сообщения об ошибках при недоступности БД.

---

## Загрузка прайс-листа в БД

Основной сценарий: загрузить CSV/Excel с колонками вида `Код`, `Цена`, `Скидка %` и т.п. в PostgreSQL.

### Пример запуска из контейнера

```bash
# контейнер api уже запущен через docker compose up
docker compose exec -T api \
  python -m scripts.load_csv \
  --csv ./data/example_price_list.csv
```

### Пример запуска локально

```bash
# в активированном .venv
export DB_HOST=127.0.0.1
export DB_PORT=15432
export DB_NAME=wine_db
export DB_USER=postgres
export DB_PASSWORD=postgres

python -m scripts.load_csv --csv path/to/your_price_list.csv
```

Что делает скрипт:

1. Читает файл, пытается определить:
   * разделитель (`;`, `,`, табуляция)
   * колонку кода товара
   * колонку цены в рублях
   * колонку скидки (если есть)
2. Создаёт «конверт» загрузки (`price_list_envelopes`) с метаданными:
   * имя файла
   * дата прайс-листа (пытается вытащить автоматически)
   * хеш файла (SHA-256) для защиты от повторной загрузки одного и того же файла
3. Делает upsert в таблицы:
   * товары (`products`)
   * цены (`product_prices`)
   * история (`inventory_history` при необходимости)
4. Обновляет статус конверта (`imported` / `failed`) и пишет количество вставленных строк.

### Поведение при ошибках

* Отсутствует колонка кода товара — выбрасывается `ValueError`, конверт помечается как `failed`.
* Файл с таким же SHA-256 уже загружен — операция пропускается, логика проверяется тестами.
* Любые ошибки БД аккуратно логируются.

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

Чтобы их включить, поднимите локальную БД (например, через `docker compose up db`)
и выставьте переменные окружения:

```bash
# включаем интеграционные тесты
export RUN_DB_TESTS=1

# хост и порт БД для приложений/скриптов
export DB_HOST=localhost
export DB_PORT=15432    # см. docker-compose.yml

# те же настройки для psql и pg_* утилит
export PGHOST=localhost
export PGPORT=15432
export PGUSER=postgres
export PGPASSWORD=postgres
export PGDATABASE=wine_db

# API-ключ для защищённых эндпоинтов (используется также интеграционными тестами)
export API_KEY=dev-local-api-key

# при необходимости можно переопределить базовый URL API
# (по умолчанию тесты используют http://localhost:18000)
# export API_URL=http://localhost:8080

pytest -m "integration" -q
```

---
## CI и качество кода

### 1. `ci.yml` — основной pipeline

Файл: `.github/workflows/ci.yml`.

Содержит несколько job’ов:

1. **tests**
   * Устанавливает Python и зависимости (`requirements.txt` + dev-зависимости)
   * Поднимает PostgreSQL через `docker compose` (service `db`)
   * Ждёт готовности БД (`pg_isready`)
   * Применяет SQL-миграции:
     ```bash
     bash db/migrate.sh   # использует PGHOST/PGPORT/PGUSER/PGDATABASE
     ```
   * Запускает `pytest` с покрытием
   * На падение тестов — выгружает логи контейнера БД артефактом

2. **pip-audit**
   * Запускает `pip-audit -r requirements.txt --strict`
   * Ломает сборку при найденных уязвимостях зависимостей.

3. **secrets**
   * Обёртка вокруг GitHub Secret Scanning / trufflehog (см. `secrets.yml`)
   * Проверяет коммиты на наличие случайно закоммиченных токенов/паролей.

### 2. `semgrep.yml` — статический анализ кода

Файл: `.github/workflows/semgrep.yml`.

* Запускает Semgrep в режиме **strict** на Python-коде и yaml-конфигурациях.
* Использует публичный набор правил `p/ci`.
* Для PR:
  * умеет работать с baseline-коммитом (чтобы репортить только новые проблемы),
  * падает, если в новом коде появляются блокирующие находки.

---

## Roadmap и ближайшие цели

Подробная дорожная карта ведётся в отдельном документе:

* [`docs/ROADMAP_v3_RU.md`](docs/ROADMAP_v3_RU.md)

Кратко по ближайшим шагам (из Roadmap):

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

1. Создаёшь ветку от `master`
   `git switch -c feature/my-task`
2. Делаешь небольшие, логичные коммиты с понятными сообщениями.
3. Перед пушем обязательно:
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
