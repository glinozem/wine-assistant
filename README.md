# Wine Assistant — API & ETL

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Release Drafter](https://github.com/glinozem/wine-assistant/actions/workflows/release-drafter.yml/badge.svg)](../../actions/workflows/release-drafter.yml)
[![Changelog on Release](https://github.com/glinozem/wine-assistant/actions/workflows/changelog-on-release.yml/badge.svg)](../../actions/workflows/changelog-on-release.yml)

Мини-сервис для поиска вин, хранения прайс-данных и истории цен/остатков.
API на Flask + PostgreSQL (pg_trgm, pgvector), загрузка Excel/CSV.

**Версия:** 0.2.0 (Спринт 2 — Production Readiness)

---

## 📑 Содержание

- [Что нового в Спринте 2](#что-нового-в-спринте-2)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
  - [1) Поднять БД](#1-поднять-бд)
  - [1.5) Применить миграции (рекомендуется!)](#15-применить-миграции-рекомендуется)
  - [2) Создать .env](#2-создать-env)
  - [3) Установить зависимости](#3-установить-зависимости)
  - [4) Загрузить данные](#4-загрузить-данные)
  - [5) Запустить API](#5-запустить-api)
  - [✅ Чеклист запуска](#-чеклист-запуска)
- [API](#api)
  - [Health & Readiness](#health--readiness)
  - [/search](#search)
  - [/catalog/search](#catalogsearch)
  - [/sku/…](#sku)
  - [Swagger / OpenAPI](#swagger--openapi)
  - [Примеры запросов](#примеры-запросов)
- [Логика цен и скидок](#логика-цен-и-скидок)
- [Adminer (SQL UI)](#adminer-sql-ui)
- [Миграции БД](#миграции-бд)
- [ETL / загрузчик](#etl--загрузчик)
- [🔧 Решение проблем](#-решение-проблем)
- [CI/CD и CHANGELOG](#cicd-и-changelog)
- [Roadmap](#roadmap)

---

## 🆕 Что нового в Спринте 2

### Production-Ready Healthchecks

Добавлены три новых эндпоинта для мониторинга и диагностики:

#### **`/live`** — Liveness Probe ✅
- Быстрая проверка (без обращения к БД)
- Возвращает статус процесса, версию API, uptime в секундах
- Используется для автоматического перезапуска контейнеров
- HTTP 200 всегда (если процесс жив)

#### **`/ready`** — Readiness Probe ✅
- Глубокая проверка готовности к обработке запросов
- Проверяет подключение к БД (< 100ms latency)
- Проверяет наличие 4 таблиц (`products`, `product_prices`, `inventory`, `inventory_history`)
- Проверяет 3 критичных индекса
- Проверяет наличие CHECK constraints
- Возвращает HTTP 200 (ready) или 503 (not ready)
- Детальная диагностика в JSON-ответе

#### **`/version`** — Версия API ✅
- Минимальный эндпоинт для получения версии
- Используется в CI/CD и мониторинге

#### **`/health`** — Legacy Endpoint ✅
- Оставлен для обратной совместимости
- Простой ответ `{"ok": true}`

---

## Требования

- **Python** 3.11+ (подойдёт 3.10/3.12, но тестируется на 3.11)
- **pip**, **virtualenv** (рекомендуется)
- **Docker** + **Docker Compose**
- Интернет для установки зависимостей (`openpyxl`, `psycopg2-binary`, …)

---

## Быстрый старт

### 1) Поднять БД

```powershell
docker compose up -d
```

**Результат:**
- БД: `127.0.0.1:15432` (host) → контейнер `db:5432`
- Adminer: http://localhost:18080

💡 **О схеме БД:** `db/init.sql` создаёт полную рабочую схему с таблицами, индексами и функциями. Для быстрого старта разработки этого достаточно. Для production-окружения **рекомендуется применить миграции** (см. шаг 1.5).

---

### 1.5) Применить миграции (рекомендуется!)

```powershell
# Применит все *.sql из db/migrations по алфавиту
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

**Миграции добавляют:**
- 🔒 **Guardrails:** Constraints на перекрытия интервалов цен, проверки неотрицательности
- 📊 **Диагностика:** Запросы для проверки целостности данных
- ⚡ **Оптимизации:** Дополнительные индексы и нормализация данных для production

---

**📌 Примечание о холодном старте:**

`db/init.sql` содержит полную схему для быстрого старта:
- ✅ Все таблицы (products, product_prices, inventory, inventory_history)
- ✅ Все колонки (включая price_list_rub, price_final_rub, stock_total, reserved, stock_free)
- ✅ Основные индексы и функции (upsert_price, upsert_inventory)
- ✅ Базовые constraints (PRIMARY KEY, FOREIGN KEY, CHECK)

**Миграции добавляют:**
- 🔒 Advanced constraints (EXCLUDE для предотвращения перекрытий временных интервалов)
- 🔍 Диагностические запросы для контроля качества данных
- 🚀 Production-специфичные оптимизации

**Вывод:**
- **Dev-окружение:** Можно работать сразу после `docker compose up -d`
- **Production:** Обязательно выполните миграции для максимальной надёжности

---

### 2) Создать .env

Скопируйте `.env.example` в `.env` и настройте:

```ini
# .env
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db

# API
API_KEY=mytestkey_минимум_32_символа_для_безопасности
FLASK_HOST=127.0.0.1
FLASK_PORT=18000
FLASK_DEBUG=1

# Версия API (для healthcheck)
APP_VERSION=0.2.0
```

---

### 3) Установить зависимости

```powershell
# Создать виртуальное окружение (рекомендуется)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Установить зависимости
pip install -r requirements.txt
```

📦 Для работы с Excel используется `openpyxl`.

---

### 4) Загрузить данные

Используйте единый скрипт `scripts/load_csv.py`.

**Excel (с учётом скидки из ячейки S5):**

```powershell
$FILE = "data\inbox\Прайс_2025_01_20.xlsx"
python scripts\load_csv.py --excel "$FILE" --asof 2025-01-20 --discount-cell S5 --prefer-discount-cell
```

**CSV (пример из комплекта):**

```powershell
python scripts\load_csv.py --csv data\sample\dw_sample_products.csv
```

---

### 5) Запустить API

```powershell
python api\app.py
# Или с настройками из .env: FLASK_HOST=127.0.0.1, FLASK_PORT=18000
```

**Проверка готовности:**

```powershell
# Базовый healthcheck
Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"

# Liveness probe
Invoke-WebRequest -Uri "http://127.0.0.1:18000/live" | ConvertFrom-Json

# Readiness probe (детальная проверка)
Invoke-WebRequest -Uri "http://127.0.0.1:18000/ready" | ConvertFrom-Json

# Версия API
Invoke-WebRequest -Uri "http://127.0.0.1:18000/version" | ConvertFrom-Json
```

---

### ✅ Чеклист запуска

Проверьте, что все шаги выполнены:

- [ ] Docker запущен
- [ ] `docker compose up -d` выполнен
- [ ] (Опционально) Миграции применены (`.\scripts\migrate.ps1`)
- [ ] `.env` создан и настроен
- [ ] Зависимости установлены (`pip install -r requirements.txt`)
- [ ] Данные загружены (`scripts\load_csv.py`)
- [ ] API запущен и отвечает на `/health`, `/live`, `/ready`

---

## API

### Health & Readiness

#### **GET /health**
Простой healthcheck для обратной совместимости.

```http
GET /health
```

**Ответ:**
```json
{
  "ok": true
}
```

---

#### **GET /live** 🆕
Liveness probe — проверяет, жив ли процесс (без обращения к БД).

```http
GET /live
```

**Ответ:**
```json
{
  "status": "alive",
  "version": "0.2.0",
  "timestamp": "2025-10-18T19:03:38.813229Z",
  "uptime_seconds": 3600
}
```

**Поля:**
- `status` — всегда "alive" (если процесс работает)
- `version` — версия API из `APP_VERSION` env
- `timestamp` — текущее время (UTC, ISO 8601)
- `uptime_seconds` — сколько секунд работает процесс

**Использование:**
- Kubernetes liveness probe
- Docker HEALTHCHECK
- Мониторинг (Prometheus, Datadog)

---

#### **GET /ready** 🆕
Readiness probe — проверяет готовность к обработке запросов.

```http
GET /ready
```

**Успешный ответ (200 OK):**
```json
{
  "status": "ready",
  "timestamp": "2025-10-18T18:17:37.635353Z",
  "version": "0.2.0",
  "checks": {
    "database": {
      "status": "up",
      "latency_ms": 3.26,
      "version": "PostgreSQL 16.10",
      "tables": [
        "inventory",
        "inventory_history",
        "product_prices",
        "products"
      ],
      "indexes": [
        "idx_inventory_code_free",
        "idx_inventory_history_code_time",
        "ux_product_prices_code_from"
      ],
      "constraints": [
        "chk_product_prices_nonneg"
      ]
    }
  },
  "response_time_ms": 48.89
}
```

**Ошибка (503 Service Unavailable):**
```json
{
  "status": "not_ready",
  "timestamp": "2025-10-18T18:22:19.438239Z",
  "version": "0.2.0",
  "checks": {
    "database": {
      "status": "down",
      "error": "connection to server at \"127.0.0.1\", port 15432 failed: Connection refused"
    }
  },
  "response_time_ms": 2038.53
}
```

**Что проверяется:**
1. ✅ Подключение к PostgreSQL
2. ✅ Версия БД (PostgreSQL 16+)
3. ✅ Наличие 4 таблиц:
   - `products`
   - `product_prices`
   - `inventory`
   - `inventory_history`
4. ✅ Наличие 3 критичных индексов:
   - `ux_product_prices_code_from` (уникальность цен по времени)
   - `idx_inventory_history_code_time` (быстрый доступ к истории остатков)
   - `idx_inventory_code_free` (фильтрация по свободным остаткам)
5. ✅ Наличие CHECK constraint:
   - `chk_product_prices_nonneg` (цены неотрицательные)

**Использование:**
- Kubernetes readiness probe
- Load balancer health checks
- CI/CD smoke tests

---

#### **GET /version** 🆕
Возвращает только версию API.

```http
GET /version
```

**Ответ:**
```json
{
  "version": "0.2.0"
}
```

**Использование:**
- Проверка версии в CI/CD
- Отображение версии в UI
- Мониторинг deployments

---

### /search

Поиск в каталоге по **финальной цене** и полнотексту:

```http
GET /search?q=<строка>&max_price=<число>&color=<цвет>&region=<регион>&limit=<n>
```

**Параметры:**
- `q` — поисковый запрос (опционально)
- `max_price` — максимальная цена (фильтр по `price_final_rub`)
- `color`, `region`, `style` — фильтры по атрибутам
- `limit` — количество результатов (по умолчанию 10)

**Особенности:**
- Фильтр по цене идёт по `price_final_rub` (финальная цена с учётом скидки)
- Релевантность — `pg_trgm.similarity` по `search_text` (+ fallback по `title_en`)

---

### /catalog/search

Расширенный поиск с пагинацией и остатками:

```http
GET /catalog/search?q=&max_price=&color=&region=&style=&grape=&in_stock=(true|false)&limit=20&offset=0
```

**Возвращает:**
```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "query": "венето"
}
```

**Дополнительно:**
- Поле `in_stock` берётся из таблицы `inventory`
- Вычисляемые поля: `stock_total`, `reserved`, `stock_free`

---

### /sku/…

**⚠️ Требуется API-ключ!**

#### Карточка товара

```http
GET /sku/<code>
Headers: X-API-Key: <ваш_ключ>
```

Возвращает всю информацию о товаре (включая `price_list_rub`, `price_final_rub`) и текущую цену из истории.

#### История цен

```http
GET /sku/<code>/price-history?limit=50&offset=0&from=YYYY-MM-DD&to=YYYY-MM-DD
Headers: X-API-Key: <ваш_ключ>
```

#### История остатков

```http
GET /sku/<code>/inventory-history?limit=50&offset=0&from=YYYY-MM-DD&to=YYYY-MM-DD
Headers: X-API-Key: <ваш_ключ>
```

---

### Swagger / OpenAPI

- `/openapi.json` — спецификация (если включили)
- `/docs` — Swagger UI (если включили `flasgger`)

**Как включить (опционально):**

```powershell
pip install flasgger
```

В `api/app.py`:

```python
from flasgger import Swagger

app = Flask(__name__)
Swagger(app, template_file='openapi.yaml')
```

---

### Примеры запросов

**PowerShell:**

```powershell
# Публичные эндпоинты (без ключа)
Invoke-WebRequest -Uri "http://127.0.0.1:18000/live" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/ready" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/version" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/search?q=венето&max_price=3000" | ConvertFrom-Json

# Защищённый эндпоинт (с ключом)
$headers = @{ "X-API-Key" = "mytestkey" }
Invoke-WebRequest -Uri "http://127.0.0.1:18000/sku/D011283" -Headers $headers | ConvertFrom-Json
```

**curl:**

```bash
# Публичные эндпоинты
curl "http://127.0.0.1:18000/live"
curl "http://127.0.0.1:18000/ready"
curl "http://127.0.0.1:18000/version"
curl "http://127.0.0.1:18000/search?q=венето&max_price=3000"

# Защищённый эндпоинт
curl -H "X-API-Key: mytestkey" http://127.0.0.1:18000/sku/D011283
```

---

## Логика цен и скидок

Система работает с **двумя ценами**:

- **`price_list_rub`** — списочная цена из прайса (колонка "Цена" или "Цена прайс")
- **`price_final_rub`** — финальная цена с учётом скидки

### Откуда берётся скидка:

Скидка применяется в порядке приоритета:

1. **Приоритет 1:** Ячейка S5 в Excel (по умолчанию) — если задана или `--prefer-discount-cell`
2. **Приоритет 2:** Вторая строка заголовка (если там указан `0%`, `5%` и т.д.)
3. **Приоритет 3:** Колонка "Цена со скидкой" из файла
4. **Fallback:** Если скидки нет — `price_final_rub = price_list_rub`

### Управление приоритетом:

```powershell
# Использовать скидку из ячейки S5 (приоритет)
python scripts\load_csv.py --excel Прайс.xlsx --prefer-discount-cell

# Или через переменную окружения
$env:PREFER_S5 = "1"
python scripts\load_csv.py --excel Прайс.xlsx

# Изменить адрес ячейки со скидкой
python scripts\load_csv.py --excel Прайс.xlsx --discount-cell T3
```

### Формула расчёта:

```
price_final_rub = price_list_rub × (1 - discount)
```

**Важно:** Все API эндпоинты фильтруют и сортируют по **финальной** цене (`price_final_rub`).

---

## Adminer (SQL UI)

**URL:** http://localhost:18080

**Параметры подключения:**
- **System:** PostgreSQL
- **Server:** `db` (внутри docker-сети)
- **User:** `postgres`
- **Password:** `dev_local_pw`
- **Database:** `wine_db`

**Для подключения с хоста (psql):**
```bash
psql -h 127.0.0.1 -p 15432 -U postgres -d wine_db
```

---

## Миграции БД

**SQL-миграции:** `db/migrations/*.sql`

**Прогон:**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

**Миграции накатывают:**
- Advanced constraints (EXCLUDE для запрета перекрытий временных интервалов)
- Нормализацию данных (effective_to в product_prices)
- Диагностические запросы для проверки целостности
- Production-специфичные оптимизации

**Примечание:** `db/init.sql` содержит базовую полную схему для разработки. Миграции добавляют дополнительные guardrails, необходимые для production.

---

## ETL / загрузчик

**Используйте только `scripts/load_csv.py`** для всех задач загрузки данных.

### Возможности:

- Поддерживает Excel и CSV
- Автоопределяет строку заголовка (даже в многострочных шапках)
- Извлекает скидку из ячейки Excel (по умолчанию S5)
- Нормализует коды товаров (валидация по regex)
- Записывает данные в:
  - `products` (оба типа цен, атрибуты)
  - `product_prices` (история цен)
  - `inventory` и `inventory_history` (остатки/резервы/свободный остаток)

### Примеры использования:

```powershell
# Загрузка с датой среза (для истории)
python scripts\load_csv.py --excel Прайс.xlsx --asof 2025-01-15

# Указать другую ячейку со скидкой
python scripts\load_csv.py --excel Прайс.xlsx --discount-cell T3

# Указать конкретный лист
python scripts\load_csv.py --excel Прайс.xlsx --sheet "Основной"
```

📝 **Устаревший скрипт:** `etl/run_daily.py` оставлен для совместимости, но функционал ограничен. Рекомендуется использовать `scripts/load_csv.py`.

---

## 🔧 Решение проблем

### Ошибка: `column "price_final_rub" does not exist`

**Причина:** Работаете со старой версией БД (созданной до Спринта 1).

**Решение:**
```powershell
# Вариант 1: Пересоздать БД (рекомендуется)
docker compose down -v
docker compose up -d

# Вариант 2: Применить миграции на существующую БД
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

---

### Ошибка: `403 Forbidden` на `/sku/<code>`

**Причина:** Эндпоинт требует API-ключ.

**Решение:**
```powershell
# PowerShell
$headers = @{ "X-API-Key" = "mytestkey" }
Invoke-WebRequest -Uri "http://127.0.0.1:18000/sku/D011283" -Headers $headers

# curl
curl -H "X-API-Key: mytestkey" http://127.0.0.1:18000/sku/D011283
```

Убедитесь, что в `.env` установлен `API_KEY`.

---

### Ошибка: `/ready` возвращает 503

**Причина:** База данных недоступна или не прошла проверки.

**Решение:**
```powershell
# 1. Проверьте, что БД запущена
docker compose ps

# 2. Проверьте детали ошибки
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/ready" -SkipHttpErrorCheck
$response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 5

# 3. Запустите БД, если остановлена
docker compose up -d

# 4. Примените миграции, если не применены
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

---

### Adminer не подключается к БД

**Проблема:** Неверный Server или порт.

**Решение:**
- **Внутри Docker:** Server = `db` (не `host.docker.internal`)
- **URL:** http://localhost:18080 (не 8080)
- **Password:** `dev_local_pw` (из `.env` → `POSTGRES_PASSWORD`)

---

### Цены не совпадают с прайсом

**Причина:** Скидка автоматически применяется из ячейки S5 или шапки файла.

**Решение:**
```powershell
# Проверьте ячейку S5 в Excel (там может быть скидка %, например 10)
# Измените приоритет источника скидки:
python scripts\load_csv.py --excel Прайс.xlsx --prefer-discount-cell

# Или отключите приоритет S5:
$env:PREFER_S5 = "0"
python scripts\load_csv.py --excel Прайс.xlsx
```

---

### API не отвечает на порту 8000

**Причина:** Нестандартный порт настроен в `.env`.

**Решение:**
- Проверьте `.env` → `FLASK_PORT=18000`
- URL должен быть: http://127.0.0.1:18000 (не 8000)

---

### CSV загружается не полностью (пропускаются строки)

**Причина:** В данных есть запятые внутри значений, которые ломают парсинг.

**Решение:**
```powershell
# Проверьте файл CSV - запятые в колонках должны быть в кавычках
# Или удалите запятые из данных (например, "Сорт А, Сорт Б" → "Сорт А Сорт Б")

# Проверьте количество загруженных записей:
docker compose exec db psql -U postgres -d wine_db -c "SELECT COUNT(*) FROM products;"
```

---

## CI/CD и CHANGELOG

- **Release Drafter** формирует черновики релизов при push в `master`
- При публикации/редактировании релиза триггерится **Changelog on Release**:
  - Генерирует `CHANGELOG.md`
  - Создаёт авто-PR `docs/changelog: <tag>`
- Для надёжного авто-PR используем PAT (fine-grained) в `secrets.ACTIONS_WRITER_PAT`
- Бейджи в начале README показывают статусы CI, Release Drafter, Changelog on Release

---

## Roadmap

### ✅ Завершено

- [x] ~~Синхронизировать `db/init.sql` с миграциями~~ ✅ Спринт 1
- [x] ~~Добавить healthcheck с проверкой БД в `/ready`~~ ✅ Спринт 2
- [x] ~~Добавить `/live` liveness probe~~ ✅ Спринт 2
- [x] ~~Добавить `/version` endpoint~~ ✅ Спринт 2

### 🚧 В работе

- [ ] Вынести CORS (`flask-cors`) для фронта
- [ ] Покрыть `scripts/load_csv.py` тестами (минимум happy-path + разбор S5 + конфликтующие цены)

### 📋 Планируется

- [ ] Консолидировать ETL: удалить устаревший `etl/run_daily.py`
- [ ] Полноценная OpenAPI-схема + аннотации у всех эндпоинтов
- [ ] Примеры клиентов (Python `requests`, JavaScript `fetch`)
- [ ] Метрики (логирование запросов, время ответа), Sentry/OTel (опционально)
- [ ] Docker Compose healthcheck для автоматического перезапуска
- [ ] Telegram-бот для поиска и получения карточек товаров
- [ ] Векторный поиск с эмбеддингами + rerank для улучшения релевантности

---

## 📝 Изменения в Спринте 2

### Добавлено

**API:**
- ✅ `GET /live` — liveness probe (uptime, версия, timestamp)
- ✅ `GET /ready` — readiness probe (БД + таблицы + индексы + constraints)
- ✅ `GET /version` — возвращает версию API
- ✅ Отслеживание uptime (`app.start_time`)

**Документация:**
- ✅ Детальное описание healthcheck эндпоинтов
- ✅ Примеры использования для Kubernetes/Docker
- ✅ Troubleshooting для 503 Service Unavailable

**Инфраструктура:**
- ✅ Переменная окружения `APP_VERSION` для версионирования

### Изменено

- 🔄 `/health` оставлен для обратной совместимости
- 🔄 Roadmap обновлён (галочки для выполненных задач)

---

## 📝 Лицензия

MIT

## 🤝 Контрибьюция

Pull requests приветствуются! Для крупных изменений сначала откройте issue для обсуждения.

---

**Сделано с ❤️ для винной индустрии** 🍷

**Версия:** 0.2.0 | **Дата:** 18 октября 2025 | **Спринт:** 2 (Production Readiness)
