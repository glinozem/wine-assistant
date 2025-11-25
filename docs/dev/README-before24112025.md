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

## Как запустить проект и тесты локально

### 1. Запустить проект (Docker Compose, рекомендовано)

```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

cp .env.example .env    # при необходимости поправьте пароли/порты
docker compose up -d --build
```

После этого API будет доступно по адресу, указанному в `docker-compose.yml`
(см. также раздел «TL;DR — как быстро запустить» выше).

---

### 2. Запустить тесты

```bash
# Базовый прогон как в CI (все тесты, кроме мониторинговых)
pytest -q -m "not monitoring"

# Только быстрые юнит-тесты (без интеграционных и мониторинговых)
pytest -q -m "not integration and not monitoring"
```

> Для интеграционных тестов, которые работают с реальной PostgreSQL,
> поднимите контейнер `db` (`docker compose up -d db`),
> установите `RUN_DB_TESTS=1` и нужные `PG*`/`DB_*` переменные окружения.
> Подробности — в `tests/README.md`.

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


### Импорт прайс-листа из Excel (пример)

Ниже — реальный рабочий сценарий для Excel‑прайса поставщика (файл
**`Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx`**). Его можно
использовать как шаблон для любых похожих прайс‑листов.

1. Поместите файл в каталог `data/inbox` в корне проекта:

   ```text
   wine-assistant/
     data/
       inbox/
         Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx
   ```

2. Убедитесь, что инфраструктура поднята и миграции применены:

   ```bash
   docker compose up -d --build

   # проверка готовности API и БД
   curl http://localhost:18000/health
   curl http://localhost:18000/ready
   ```

3. С хоста настройте переменные окружения для подключения к PostgreSQL
   (порт `15432` проброшен из контейнера `db`):

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

4. Запустите импорт Excel‑файла:

   ```bash
   python -m scripts.load_csv --excel "./data/inbox/Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx"
   ```

   В логе вы увидите примерно следующее:

   ```text
   [date] Effective date: 2025-01-20 (source: auto-extracted)
   [excel] sheet=0, header_row=3, ...
   [discount] header=None  cell(S5)=0.0  -> used=0.0

   [OK] Import completed successfully
      Envelope ID: da3b9d32-08f4-4ca9-bfaa-16ca1e13f168
      Rows processed: 266
      Effective date: 2025-01-20
   ```

5. После успешного импорта данные оказываются в нескольких таблицах:

   * `products` — карточки товаров (код, название, страна и т.д.).
     Пример проверки:

     ```sql
     SELECT code, title_ru, country, price_final_rub
     FROM products
     WHERE code = 'D009704';
     ```

   * `product_prices` — история цен по каждому SKU:

     ```sql
     SELECT code, price_rub, effective_from, effective_to
     FROM product_prices
     WHERE code = 'D009704'
     ORDER BY effective_from;
     ```

     Для примера выше результат будет с одной записью
     `price_rub = 2778.0`, `effective_from = '2025-01-20'`,
     `effective_to IS NULL`.

   * `ingest_envelope` — техническая таблица с информацией о файле
     (имя, SHA‑256, статус, сколько строк обработано):

     ```sql
     SELECT envelope_id, file_name, status, rows_inserted
     FROM ingest_envelope
     ORDER BY upload_timestamp DESC
     LIMIT 5;
     ```

   * `price_list` — метаданные прайс‑листа (одна запись на файл):

     ```sql
     SELECT price_list_id, envelope_id, effective_date, discount_percent
     FROM price_list
     ORDER BY effective_date DESC
     LIMIT 5;
     ```

6. Для проверки со стороны API можно воспользоваться эндпоинтом
   `/api/v1/sku/<code>/price-history`:

   ```bash
   curl -H "X-API-Key: $API_KEY"      "http://localhost:18000/api/v1/sku/D009704/price-history"
   ```

   Ответ будет содержать историю цен по коду, например:

   ```json
   {
     "code": "D009704",
     "items": [
       {
         "code": "D009704",
         "effective_from": "Mon, 20 Jan 2025 00:00:00 GMT",
         "effective_to": null,
         "price_rub": "2778.0"
       }
     ],
     "limit": 50,
     "offset": 0,
     "total": 1
   }
   ```

### Идемпотентность загрузки прайс-листов

Скрипт `load_csv` считает SHA‑256 от содержимого файла и записывает его
в `ingest_envelope.file_sha256`. Если точно такой же файл уже загружен,
повторный запуск завершится сообщением:

```text
>> SKIP: File already imported
   Envelope ID: ...
   Status: success
   ...
   This file has already been processed. No action taken.
```

Это защищает от случайной повторной загрузки одного и того же прайса.

Если нужно **насильно переработать тот же файл** (например, после изменения
ETL‑логики), можно удалить соответствующий конверт и связанную запись
в `price_list`:

```sql
DELETE FROM price_list
WHERE envelope_id = '<нужный_envelope_id>';

DELETE FROM ingest_envelope
WHERE envelope_id = '<нужный_envelope_id>';
```

После этого `load_csv` обработает файл заново.

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

Интеграционные тесты работы с PostgreSQL помечены `@pytest.mark.integration` и по умолчанию **пропускаются**.
Чтобы их включить, поднимите локальную БД (например, через `docker compose up db`) и выставьте:

```bash
export RUN_DB_TESTS=1
export PGHOST=localhost
export PGPORT=15432    # см. docker-compose.yml
export PGUSER=postgres
export PGPASSWORD=postgres
export PGDATABASE=wine_db

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


## Быстрый старт для разработчика

Типичный цикл разработки:

1. Поднять локальное окружение (PostgreSQL + API).
2. Прогнать быстрые юнит-тесты.
3. При необходимости — интеграционные тесты без «долгих» сценариев.

Для этого есть удобные цели в `Makefile`:

```bash
# Поднять dev-окружение (Docker Compose, БД, API)
make dev-up

# Только юнит-тесты (без PostgreSQL и HTTP-API)
make test-unit

# Интеграционные тесты без помеченных как slow сценариев
make test-int-noslow
```

Пояснения:

* `make dev-up` поднимает docker-окружение для разработки (БД + API) и подготавливает его к работе.
* `make test-unit` запускает только юнит-тесты, которые не требуют живой БД или HTTP-API.
* `make test-int-noslow` выполняет интеграционные тесты, исключая самые медленные (`@pytest.mark.slow`).

> Для интеграционных тестов убедитесь, что:
> * в `RUN_DB_TESTS` установлено значение `1` в окружении;
> * корректно настроены `DB_*` / `PG*` переменные (хост, порт, логин/пароль);
> * API доступно по `API_URL` / `API_BASE_URL`, а `API_KEY` совпадает со значением в `.env`.
> Подробная инструкция — в разделе «Тестирование» ниже.

## Мини-чеклист: от чистого клона до зелёных тестов

Этот раздел — короткая памятка «как получить зелёные тесты» на свежей машине.

1. **Клонируем репозиторий**

   ```bash
   git clone https://github.com/glinozem/wine-assistant.git
   cd wine-assistant
   ```

2. **Готовим `.env`** (на основе примера)

   ```bash
   cp .env.example .env
   # при необходимости поправьте пароли, порты и API_KEY
   ```

3. **Поднимаем инфраструктуру (PostgreSQL + migrator, при желании API)**

   Минимально для тестов достаточно БД и мигратора:

   ```bash
   docker compose up -d db migrator
   ```

   либо весь стек (БД + API + вспомогательные сервисы):

   ```bash
   docker compose up -d
   ```

   Убедитесь, что сервис `db` в состоянии `healthy`:

   ```bash
   docker compose ps
   ```

4. **Ждём применения миграций и загрузки демо-данных**

   Сервис `migrator` внутри Docker:

   * ждёт готовности Postgres (`pg_isready`),
   * применяет все SQL-миграции из `db/migrations/`,
   * при необходимости наполняет БД минимальным набором тестовых данных
     (SKU, цены, история) — чтобы интеграционные тесты могли сразу работать.

5. **Создаём и активируем виртуальное окружение Python (по желанию)**

   ```bash
   python -m venv .venv
   source .venv/bin/activate           # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

6. **Экспортируем переменные окружения для тестов**

   Используем контейнерную БД, проброшенную на `localhost:15432`:

   Linux / macOS:

   ```bash
   export RUN_DB_TESTS=1
   export PGHOST=localhost
   export PGPORT=15432        # см. docker-compose.yml
   export PGUSER=postgres
   export PGPASSWORD=postgres
   export PGDATABASE=wine_db
   ```

   Windows PowerShell:

   ```powershell
   $env:RUN_DB_TESTS   = "1"
   $env:PGHOST         = "localhost"
   $env:PGPORT         = "15432"
   $env:PGUSER         = "postgres"
   $env:PGPASSWORD     = "postgres"
   $env:PGDATABASE     = "wine_db"
   ```

7. **Запускаем тесты**

   ```bash
   pytest -q -rs
   ```

   При успехе в конце вы увидите отчёт вида:

   ```text
   ====== N passed, M skipped in XX.XXs ======
   ```

   Это и есть «зелёные тесты» на актуальной схеме БД и реальных данных прайс-листа.

---

## Migrator: как применяются миграции в Docker и CI

Помимо скриптов `db/migrate.sh` / `db/migrate.ps1` в проекте есть вспомогательный
Docker-сервис **`migrator`**, который отвечает за применение SQL-миграций к
PostgreSQL в контейнере.

Кратко, что он делает:

* ждёт, пока сервис `db` станет доступен (`pg_isready`);
* последовательно применяет все миграции из `db/migrations/`
  (и при необходимости `db/init.sql`);
* записывает информацию о применённых файлах в служебную таблицу
  `schema_migrations`, делая процесс идемпотентным.

Типичные сценарии:

* **Локальная разработка** — достаточно выполнить:

  ```bash
  docker compose up -d db migrator
  ```

  или просто

  ```bash
  docker compose up -d
  ```

  Миграции будут применены автоматически, после чего можно запускать API и тесты.

* **CI** — в пайплайне GitHub Actions поднимается `db`, запускается `migrator`,
  и только после успешного завершения миграций запускаются тесты (`pytest`).

Если нужно прогнать миграции вручную (например, против локальной PostgreSQL
без Docker), можно использовать существующие скрипты:

```bash
bash db/migrate.sh          # Linux / macOS
pwsh db/migrate.ps1         # Windows PowerShell
```

Они создают необходимые расширения (`pg_trgm`, `pgcrypto`, `vector`),
поддерживают таблицу `schema_migrations` и аккуратно применяют все SQL-файлы.

---

## Карантин прайс-листа (`price_list_quarantine`)

Для отслеживания проблемных строк прайс-листа используется таблица
**`price_list_quarantine`** (создаётся миграцией `0010_price-list-quarantine.sql`).

Общий принцип работы:

1. `scripts/load_csv.py` читает файл (Excel/CSV) и валидирует каждую строку:
   проверяет наличие кода товара, корректность цены, скидки, формата даты и т.п.
2. Если строка **не проходит валидацию** и не может быть безопасно загружена
   в основные таблицы (`products`, `product_prices`, при необходимости `inventory`),
   она **не попадает** в боевые витрины.
3. Вместо этого сырые данные + описание ошибки сохраняются в
   `price_list_quarantine` вместе с идентификатором «конверта» (`ingest_envelope`).

Типичная структура полей (может расширяться по мере развития ETL):

* `envelope_id` — ссылка на запись в `ingest_envelope` (конкретный файл/загрузка);
* `row_number` — номер строки в исходном файле;
* `raw_payload` — сырые данные строки (обычно JSON или текст);
* `error_message` — краткое описание причины, по которой строка ушла в карантин;
* служебные поля (`created_at` и т.п.).

Пример запроса для анализа последних ошибок:

```sql
SELECT envelope_id,
       row_number,
       error_message,
       created_at,
       raw_payload
FROM price_list_quarantine
ORDER BY created_at DESC
LIMIT 50;
```

Зачем это нужно:

* **безопасность данных** — кривые строки не ломают основные таблицы;
* **прозрачность** — всегда можно посмотреть, какие именно строки не загрузились и почему;
* **отладка и поддержка** — по содержимому карантина легко воспроизвести ошибку,
  добавить новые правила валидации или поправить исходные данные у поставщика.
