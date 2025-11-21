# Wine Assistant — API & ETL для прайс-листа вина

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Semgrep](https://github.com/glinozem/wine-assistant/actions/w...ows/semgrep.yml/badge.svg)](../../actions/workflows/semgrep.yml)
[![Secrets](https://github.com/glinozem/wine-assistant/actions/w...ows/secrets.yml/badge.svg)](../../actions/workflows/secrets.yml)

Небольшой учебный проект: REST-API для работы с прайс-листом вина + ETL-скрипт для загрузки данных из Excel/CSV в PostgreSQL.
Проект используется как «песочница» для практики по:

* проектированию API и документации (Flask + Swagger)
* работе с PostgreSQL, миграциями и Docker Compose
* нагрузочному и интеграционному тестированию (pytest, requests)
* CI/CD (GitHub Actions, Semgrep, pip-audit, secret-scan)
* постепенному «оживлению» продукта через Roadmap и спринты.

**Текущий статус:** учебный pet-project, активно дорабатывается.
Подробный Roadmap: [`docs/ROADMAP_v3_RU.md`](docs/ROADMAP_v3_RU.md).

---

## Архитектура и компоненты

Проект состоит из нескольких частей:

1. **REST API (Flask)** — выдаёт информацию о винах и ценах:
   * поиск по названию / фильтрам,
   * получение карточки SKU,
   * история цен по SKU.
2. **ETL-скрипт `load_csv`** — парсит Excel/CSV прайс-лист поставщика и грузит данные в PostgreSQL:
   * нормализует названия колонок,
   * приводит типы,
   * пишет историю цен в отдельную таблицу,
   * обеспечивает идемпотентность загрузки (по SHA‑256 файла).
3. **PostgreSQL** — основная БД проекта.
4. **Docker Compose** — поднимает API и БД в локальном окружении.
5. **Набор тестов** — unit + integration, проверяют как бизнес-логику, так и end‑to‑end сценарии.

Из важных сущностей в БД:

* `products` — каталог товаров (SKU, производитель, название, страна, объём, алкоголь, текущие цены и т.д.).
* `product_prices` — история цен по каждому SKU с полями `effective_from` / `effective_to`.
* `ingest_envelope` — «конверт» загрузки одного файла (SHA‑256, статус, ошибки и т.п.).
* `price_list` — заголовок прайс-листа (дата действия, глобальная скидка, связь с `ingest_envelope`).

---

## Быстрый старт (через Docker Compose)

Требуется: Docker / Docker Desktop и docker compose.

1. Клонируйте репозиторий и перейдите в каталог проекта:

   ```bash
   git clone https://github.com/glinozem/wine-assistant.git
   cd wine-assistant
   ```

2. Создайте `.env` на основе примера:

   ```bash
   cp .env.example .env
   ```

   В `.env` задаются, в том числе:

   ```env
   # Параметры БД для API и скриптов
   DB_HOST=db
   DB_PORT=5432
   DB_NAME=wine_db
   DB_USER=postgres
   DB_PASSWORD=postgres

   # API key для защищённых эндпоинтов
   API_KEY=your-secret-api-key-minimum-32-chars
   ```

3. Поднимите контейнеры:

   ```bash
   docker compose up -d
   ```

   После этого:

   * API будет доступно по адресу: `http://localhost:18000`
   * health‑эндпоинты:
     ```bash
     curl http://localhost:18000/health
     curl http://localhost:18000/ready
     ```
   * PostgreSQL будет доступна на хосте `localhost`, порт `15432` (проброшен из контейнера `db`).

4. Настройте переменные окружения для доступа к БД **с хоста** (пример для PowerShell):

   ```powershell
   $env:PGHOST      = "localhost"
   $env:PGPORT      = "15432"
   $env:PGDATABASE  = "wine_db"
   $env:PGUSER      = "postgres"
   $env:PGPASSWORD  = "postgres"
   ```

   В Linux/macOS это те же переменные через `export`:

   ```bash
   export PGHOST=localhost
   export PGPORT=15432
   export PGDATABASE=wine_db
   export PGUSER=postgres
   export PGPASSWORD=postgres
   ```

5. Проверка подключения к БД:

   ```bash
   psql -c "SELECT 1;"
   ```

6. Проверка основных таблиц (пример):

   ```bash
   psql -c "\dt"
   ```

---

## Локальный запуск без Docker

Требуется: Python 3.11+ и локальная PostgreSQL.

1. Клонируйте проект:

   ```bash
   git clone https://github.com/glinozem/wine-assistant.git
   cd wine-assistant
   ```

2. Создайте и активируйте виртуальное окружение:

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Linux/macOS
   # или
   .venv\Scripts\Activate.ps1   # Windows PowerShell
   ```

3. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

4. Настройте локальную PostgreSQL (создайте базу `wine_db`) и выставьте переменные окружения:

   ```bash
   export PGHOST=localhost
   export PGPORT=5432
   export PGDATABASE=wine_db
   export PGUSER=postgres
   export PGPASSWORD=postgres
   ```

   или через `.env` / системные средства конфигурации.

5. Примените миграции (если они есть в каталоге `db/`):

   ```bash
   bash db/migrate.sh
   ```

6. Запустите API локально:

   ```bash
   flask --app app run --port 18000
   ```

   После этого API будет доступно на `http://localhost:18000`.

---

## Структура каталогов

Кратко по основным каталогам:

```text
.
├── app/                  # Flask-приложение и API
│   ├── routes/           # маршруты и обработчики
│   ├── models/           # модели БД
│   └── ...
├── scripts/              # ETL-скрипты (load_csv, утилиты и т.д.)
├── db/                   # SQL-миграции, вспомогательные скрипты
├── tests/                # unit- и integration-тесты
│   ├── unit/
│   └── integration/
├── docs/                 # Roadmap, заметки, вспомогательная документация
└── ...
```

Основные файлы:

* `scripts/load_csv.py` — точка входа для загрузки прайс‑листа.
* `scripts/load_utils.py` — общие вспомогательные функции ETL (подключение к БД, upsert и т.п.).
* `app/routes/products.py` — основные эндпоинты по товарам и ценам.

---

## Загрузка прайс-листа в БД

Основной сценарий: есть Excel/CSV-файл от поставщика, нужно загрузить его в БД, сохранив историю цен.

### Поддерживаемые форматы и колоноки

Скрипт `load_csv` умеет читать:

* `.xlsx` (Excel)
* `.csv` (разделитель — `;` или `,`, кодировка auto-detect)

Входной файл должен содержать как минимум **одну колонку с кодом товара**.
Поддерживаются различные варианты названий, например:

* `Код`
* `Артикул`
* `Code`
* `SKU`

Их все нормализует `_canonicalize_headers()`.

Для цен поддерживаются варианты:

* `Цена`
* `Цена прайс`
* `Цена, руб.`
* `Price`
* и т.д.

Колонка с ценой со скидкой может называться, например, `Цена со скидкой`, `Цена со скидкой 10%` и т.п.

### Пример запуска ETL

```bash
# через модульный вызов
python -m scripts.load_csv --csv path/to/price.xlsx

# или напрямую
python scripts/load_csv.py --csv path/to/price.xlsx
```

Скрипт:

1. Определяет формат файла и читает данные в DataFrame.
2. Нормализует заголовки (на русском и английском).
3. Приводит типы (цены -> float, объём/градусы -> float, остатки -> int).
4. Создаёт «конверт» (`ingest_envelope`) для файла.
5. Заполняет `price_list` на основе даты и скидки.
6. Обновляет `products` и `product_prices` (создавая новый шаг истории цен).

После успешного импорта в stdout печатается краткий отчёт:

```text
[OK] Import completed successfully
   Envelope ID: <uuid>
   Rows processed: <N>
   Effective date: YYYY-MM-DD
```

### История цен и `product_prices`

Таблица `product_prices` хранит историю изменения цен:

* `code` — SKU
* `price_rub` — цена на момент действия
* `effective_from` — дата/время, с которой действует цена
* `effective_to` — дата/время, до которой действует цена (или `NULL`, если это текущая цена)

Скрипт использует хранимую процедуру `upsert_price(code, price_rub, effective_from)`, которая:

* закрывает предыдущий открытый период (`effective_to`),
* создаёт новый шаг с `effective_from = <дата прайса>` и `effective_to = NULL`,
* учитывает уникальный индекс `(code, effective_from)`.

### Идемпотентность загрузки прайс-листов

Скрипт `load_csv` считает SHA‑256 от содержимого файла и записывает его
в `ingest_envelope.file_sha256`. Если точно такой же файл уже грузился
раньше (такая же SHA‑256), повторная загрузка пропускается.

Проверка реализована в коде и покрыта интеграционными тестами.

Если файл изменился хотя бы на один байт, SHA‑256 будет другой и новый
прайс‑лист будет обработан как новый «конверт».

### Поведение при ошибках

* Отсутствует колонка кода товара — выбрасывается `ValueError`, конверт помечается как `failed`.
* Файл с таким же SHA‑256 уже загружен — операция пропускается, логика проверяется тестами.
* Любые ошибки БД аккуратно логируются.

---

## Аутентификация и API_KEY

Часть эндпоинтов API (например, `/api/v1/sku/<code>` и `/api/v1/sku/<code>/price-history`) защищены простым API‑ключом.

1. Сгенерируйте ключ и пропишите его в `.env`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   ```env
   API_KEY=your-secret-api-key-minimum-32-chars
   ```

2. Передавайте ключ в заголовке `X-API-Key`:

   ```bash
   curl      -H "X-API-Key: $API_KEY"      "http://localhost:18000/api/v1/sku/D000081/price-history"
   ```

В интеграционных тестах используется тот же ключ из переменной окружения `API_KEY`.
Убедитесь, что значение в `.env` и в окружении shell совпадает.

---

## Тестирование

Вся логика покрыта pytest’ом: как API, так и ETL-часть.

### Локальный запуск без интеграционных тестов

```bash
# все тесты, кроме тех, что требуют реальную БД / API
pytest -q

# только быстрые юнит-тесты
pytest tests/unit -q
```

Интеграционные тесты, которые работают с PostgreSQL (и иногда с живым HTTP‑API),
помечены `@pytest.mark.integration` и по умолчанию **пропускаются**.

### Интеграционные тесты с PostgreSQL и API

1. Поднимите окружение через Docker Compose (БД и API):

   ```bash
   docker compose up -d db api
   ```

2. Выставьте переменные окружения в текущей shell‑сессии:

   ```bash
   # 1. Включаем интеграционные тесты
   export RUN_DB_TESTS=1

   # 2. Хост и порт БД для приложений/скриптов (проброшенный порт Docker)
   export DB_HOST=localhost
   export DB_PORT=15432    # см. docker-compose.yml

   # 3. Те же настройки для psql и pg_* утилит
   export PGHOST=localhost
   export PGPORT=15432
   export PGUSER=postgres
   export PGPASSWORD=postgres      # или ваш пароль из .env
   export PGDATABASE=wine_db

   # 4. Базовый URL API и ключ авторизации
   export API_URL=http://localhost:18000
   export API_BASE_URL=http://localhost:18000
   export API_KEY=your-secret-api-key-minimum-32-chars
   ```

   > Важно: `API_KEY` здесь должен совпадать со значением `API_KEY` в `.env`,
   > которое использует контейнер `api`.

3. Запустите интеграционные тесты:

   ```bash
   # все интеграционные тесты
   pytest -m "integration" -vv

   # только ETL- и price-history сценарии
   pytest tests/integration/test_price_import_etl.py -m "integration" -vv

   # все интеграционные, но без особо долгих (помечены @pytest.mark.slow)
   pytest -m "integration and not slow" -vv
   ```

Интеграционные сценарии включают в себя, например:

* end‑to‑end импорт прайс‑листа:
  * генерация временного CSV;
  * запуск `load_csv_main()` с реальными параметрами;
  * проверка, что данные попали в `products`, `product_prices`, `ingest_envelope`;
* проверку идемпотентности:
  * повторный импорт того же файла не создаёт дублей и не ломает историю цен;
* историю цен:
  * подготовка нескольких прайсов с разными датами и ценами,
  * проверка, что таблица `product_prices` содержит корректную историю,
  * сравнение истории из БД с ответом эндпоинта
    `GET /api/v1/sku/<code>/price-history`;
* мониторинговые тесты на реальных SKU (`D000081`, `D009704` и т.п.):
  * сравнение текущей цены и истории по данным БД и API.

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
   * Проверяет коммиты на наличие случайно закоммиченных секретов.

4. **semgrep**
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

1. **Улучшение DX (developer experience)**:
   * доработать ошибки валидации,
   * сделать более «говорящие» ответы API,
   * улучшить документацию по запуску и настройке.
2. **Расширение бизнес-логики**:
   * добавить больше фильтров и сортировок в поиске,
   * доработать модель данных (страны, регионы, сорта винограда).
3. **Нагрузочное тестирование и оптимизации**:
   * померить производительность на больших прайс-листах,
   * оптимизировать сложные запросы и индексы.
4. **Дополнительные фичи** (по мере необходимости):
   * webhook’и / события при изменении цен,
   * выгрузка отчётов,
   * интеграция с внешними системами.

---

## Лицензия

Учебный проект, лицензия: **MIT** (см. файл `LICENSE`).

Проект можно использовать как основу для собственных pet‑проектов, экспериментов с CI/CD и отработки навыков backend‑разработки.
