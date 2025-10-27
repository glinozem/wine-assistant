# Wine Assistant — API & ETL

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Release Drafter](https://github.com/glinozem/wine-assistant/actions/workflows/release-drafter.yml/badge.svg)](../../actions/workflows/release-drafter.yml)
[![Changelog on Release](https://github.com/glinozem/wine-assistant/actions/workflows/changelog-on-release.yml/badge.svg)](../../actions/workflows/changelog-on-release.yml)

Мини-сервис для поиска вин, хранения прайс-данных и истории цен/остатков.
API на Flask + PostgreSQL (pg_trgm, pgvector), загрузка Excel/CSV.

**Версия:** 0.4.0 (Спринт 3 — Security & Rate Limiting)

---

## 📑 Содержание

- [Что нового в Спринте 3](#что-нового-в-спринте-3)
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
  - [Rate Limiting](#rate-limiting)
  - [/search](#search)
  - [/catalog/search](#catalogsearch)
  - [/sku/…](#sku)
  - [Swagger / OpenAPI](#swagger--openapi)
  - [Примеры запросов](#примеры-запросов)
- [Логика цен и скидок](#логика-цен-и-скидок)
- [CORS Configuration](#cors-configuration)
- [Docker Health Monitoring](#docker-health-monitoring)
- [Docker API Service](#docker-api-service)
- [Adminer (SQL UI)](#adminer-sql-ui)
- [Миграции БД](#миграции-бд)
- [ETL / загрузчик](#etl--загрузчик)
- [🔧 Решение проблем](#-решение-проблем)
- [CI/CD и CHANGELOG](#cicd-и-changelog)
- [Roadmap](#roadmap)

---

## 🆕 Что нового в Спринте 3

### Rate Limiting & Security

Добавлена защита от злоупотреблений и DDoS-атак:

#### **Rate Limiting** 🔒
- **Публичные эндпоинты:** 100 запросов/час (можно настроить)
- **Защищённые эндпоинты (API key):** 1000 запросов/час (можно настроить)
- **Rate limit headers:** Автоматические заголовки в каждом ответе:
  - `X-RateLimit-Limit` — максимум запросов
  - `X-RateLimit-Remaining` — осталось запросов
  - `X-RateLimit-Reset` — Unix timestamp сброса
  - `Retry-After` — секунд до сброса
- **HTTP 429:** При превышении лимита возвращается `Too Many Requests`
- **Гибкая настройка:** Через environment variables (включение/выключение, изменение лимитов)
- **Production-ready:** Поддержка Redis для распределённых систем

#### **Security Improvements** 🛡️
- Исправлены SQL injection уязвимости в history endpoints
- Добавлены Semgrep аннотации для false positives
- Улучшена валидация пользовательского ввода

---

## Требования

- **Python** 3.11+ (подойдёт 3.10/3.12, но тестируется на 3.11)
- **pip**, **virtualenv** (рекомендуется)
- **Docker** + **Docker Compose**
- Интернет для установки зависимостей (`openpyxl`, `psycopg2-binary`, `Flask-Limiter`, …)

---

## Быстрый старт

### 1) Поднять БД
```powershell
docker compose up -d
```

**Результат:**
- БД: `127.0.0.1:15432` (host) → контейнер `db:5432`
- Adminer: http://localhost:18080

**🏥 Healthcheck:**
- Автоматическая проверка здоровья БД каждые 10 секунд
- Adminer запускается только после готовности БД
- Автоматический перезапуск при сбоях (`restart: unless-stopped`)

**Проверка статуса:**
```powershell
# Должен быть статус (healthy)
docker compose ps
```

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
APP_VERSION=0.4.0

# CORS (для фронтенда)
CORS_ORIGINS=*  # Разработка: * | Production: https://myapp.com,http://localhost:3000

# Rate Limiting (новое в v0.4.0)
RATE_LIMIT_ENABLED=1                    # Включить/выключить (1/0)
RATE_LIMIT_PUBLIC=100/hour             # Лимит для публичных endpoints
RATE_LIMIT_PROTECTED=1000/hour         # Лимит для защищённых endpoints
# RATE_LIMIT_STORAGE_URL=redis://localhost:6379  # Redis для production (опционально)
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

📦 Зависимости включают:
- `openpyxl` — работа с Excel
- `Flask-Limiter` — rate limiting
- `flasgger` — Swagger UI

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

# Проверка rate limit headers
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
Write-Host "Rate Limit: $($response.Headers['X-RateLimit-Limit'])"
Write-Host "Remaining: $($response.Headers['X-RateLimit-Remaining'])"
```

---

### ✅ Чеклист запуска

Проверьте, что все шаги выполнены:

- [ ] Docker запущен
- [ ] `docker compose up -d` выполнен
- [ ] (Опционально) Миграции применены (`.\scripts\migrate.ps1`)
- [ ] `.env` создан и настроен (включая `RATE_LIMIT_*` переменные)
- [ ] Зависимости установлены (`pip install -r requirements.txt`)
- [ ] Данные загружены (`scripts\load_csv.py`)
- [ ] API запущен и отвечает на `/health`, `/live`, `/ready`
- [ ] Rate limiting работает (проверьте headers `X-RateLimit-*`)

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

**Rate Limit:** 100 запросов/час (публичный endpoint)

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
  "version": "0.4.0",
  "timestamp": "2025-10-28T19:03:38.813229Z",
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

**Rate Limit:** 100 запросов/час

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
  "timestamp": "2025-10-28T18:17:37.635353Z",
  "version": "0.4.0",
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
  "timestamp": "2025-10-28T18:22:19.438239Z",
  "version": "0.4.0",
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
3. ✅ Наличие 4 таблиц
4. ✅ Наличие 3 критичных индексов
5. ✅ Наличие CHECK constraint

**Rate Limit:** 100 запросов/час

---

#### **GET /version** 🆕
Возвращает только версию API.

```http
GET /version
```

**Ответ:**
```json
{
  "version": "0.4.0"
}
```

**Rate Limit:** 100 запросов/час

---

### Rate Limiting

API защищён от злоупотреблений с помощью rate limiting.

#### **Лимиты запросов:**

| Тип endpoint | Лимит по умолчанию | Примеры |
|--------------|-------------------|---------|
| **Публичные** | 100 запросов/час | `/health`, `/search`, `/catalog/search` |
| **Защищённые (API key)** | 1000 запросов/час | `/sku/*`, `/sku/*/price-history` |

#### **Rate limit headers:**

Каждый ответ содержит информацию о текущем статусе лимитов:

```http
X-RateLimit-Limit: 100              # Максимум запросов в час
X-RateLimit-Remaining: 99           # Осталось запросов
X-RateLimit-Reset: 1730138509       # Unix timestamp сброса счётчика
Retry-After: 3600                   # Секунд до сброса
```

**Проверка headers в PowerShell:**
```powershell
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
Write-Host "Limit: $($response.Headers['X-RateLimit-Limit'])"
Write-Host "Remaining: $($response.Headers['X-RateLimit-Remaining'])"
Write-Host "Reset: $($response.Headers['X-RateLimit-Reset'])"
```

---

#### **HTTP 429 — Too Many Requests**

При превышении лимита API возвращает:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json; charset=utf-8
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1730138509
Retry-After: 3600

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please try again later.",
  "retry_after": "3600"
}
```

**Поля:**
- `error` — тип ошибки (всегда "rate_limit_exceeded")
- `message` — описание для пользователя
- `retry_after` — секунд до сброса счётчика

---

#### **Настройка через environment variables:**

```ini
# .env
RATE_LIMIT_ENABLED=1                    # Включить/выключить (1/0)
RATE_LIMIT_PUBLIC=100/hour             # Лимит для публичных endpoints
RATE_LIMIT_PROTECTED=1000/hour         # Лимит для защищённых endpoints
# RATE_LIMIT_STORAGE_URL=redis://localhost:6379  # Redis для production (опционально)
```

**Примеры настройки:**

```ini
# Увеличенные лимиты для dev окружения
RATE_LIMIT_PUBLIC=1000/hour
RATE_LIMIT_PROTECTED=10000/hour

# Более строгие лимиты для production
RATE_LIMIT_PUBLIC=50/hour
RATE_LIMIT_PROTECTED=500/hour

# Лимиты по минутам вместо часов
RATE_LIMIT_PUBLIC=10/minute
RATE_LIMIT_PROTECTED=100/minute

# Отключение rate limiting (только для тестирования!)
RATE_LIMIT_ENABLED=0
```

---

#### **Production: Redis Storage**

Для распределённых систем (несколько инстансов API за load balancer) используйте Redis:

```ini
# .env
RATE_LIMIT_STORAGE_URL=redis://redis-host:6379/0
```

**Docker Compose с Redis:**
```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"

  api:
    environment:
      - RATE_LIMIT_STORAGE_URL=redis://redis:6379/0
    depends_on:
      - redis
```

**Преимущества Redis:**
- ✅ Общий счётчик для всех инстансов API
- ✅ Атомарные операции (thread-safe)
- ✅ Автоматическое истечение TTL
- ✅ Персистентность счётчиков при перезапуске

---

#### **Отключение rate limiting**

Для локальной разработки или тестирования:

```powershell
# Через environment variable
$env:RATE_LIMIT_ENABLED = "0"
python api\app.py

# Или в .env
RATE_LIMIT_ENABLED=0
```

⚠️ **Внимание:** Никогда не отключайте rate limiting в production!

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

**Rate Limit:** 100 запросов/час

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

**Rate Limit:** 100 запросов/час

---

### /sku/…

**⚠️ Требуется API-ключ!**

#### Карточка товара

```http
GET /sku/<code>
Headers: X-API-Key: <ваш_ключ>
```

Возвращает всю информацию о товаре (включая `price_list_rub`, `price_final_rub`) и текущую цену из истории.

**Rate Limit:** 1000 запросов/час (для клиентов с API key)

#### История цен

```http
GET /sku/<code>/price-history?limit=50&offset=0&from=YYYY-MM-DD&to=YYYY-MM-DD
Headers: X-API-Key: <ваш_ключ>
```

**Rate Limit:** 1000 запросов/час

#### История остатков

```http
GET /sku/<code>/inventory-history?limit=50&offset=0&from=YYYY-MM-DD&to=YYYY-MM-DD
Headers: X-API-Key: <ваш_ключ>
```

**Rate Limit:** 1000 запросов/час

---

### Swagger / OpenAPI

- `/docs` — Swagger UI с интерактивной документацией
- `/openapi.json` — OpenAPI 3.0 спецификация

**Доступ:** http://127.0.0.1:18000/docs

**Функции Swagger UI:**
- 📖 Просмотр всех endpoints
- 🔒 Тестирование с API key
- 📝 Примеры запросов/ответов
- 🎯 Try it out — выполнение запросов напрямую из UI

---

### Примеры запросов

**PowerShell:**

```powershell
# Публичные эндпоинты (без ключа)
Invoke-WebRequest -Uri "http://127.0.0.1:18000/live" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/ready" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/version" | ConvertFrom-Json
Invoke-WebRequest -Uri "http://127.0.0.1:18000/search?q=венето&max_price=3000" | ConvertFrom-Json

# Проверка rate limit headers
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
Write-Host "Limit: $($response.Headers['X-RateLimit-Limit'])"
Write-Host "Remaining: $($response.Headers['X-RateLimit-Remaining'])"

# Защищённый эндпоинт (с ключом)
$headers = @{ "X-API-Key" = "mytestkey" }
Invoke-WebRequest -Uri "http://127.0.0.1:18000/sku/D011283" -Headers $headers | ConvertFrom-Json

# Тест превышения лимита (выполните 101 раз)
1..101 | ForEach-Object {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
        Write-Host "Request $_ : Remaining = $($r.Headers['X-RateLimit-Remaining'])" -ForegroundColor Green
    } catch {
        Write-Host "Request $_ : Rate limit exceeded (429)" -ForegroundColor Red
    }
}
```

**curl:**

```bash
# Публичные эндпоинты
curl "http://127.0.0.1:18000/live"
curl "http://127.0.0.1:18000/ready"
curl "http://127.0.0.1:18000/version"
curl "http://127.0.0.1:18000/search?q=венето&max_price=3000"

# Проверка rate limit headers
curl -I "http://127.0.0.1:18000/health"

# Защищённый эндпоинт
curl -H "X-API-Key: mytestkey" http://127.0.0.1:18000/sku/D011283

# Тест rate limiting
for i in {1..101}; do
  curl -w "%{http_code}\n" -o /dev/null -s "http://127.0.0.1:18000/health"
done
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

## CORS Configuration

### Что такое CORS?

CORS (Cross-Origin Resource Sharing) — механизм, позволяющий браузерам делать запросы к API с других доменов.

**Зачем нужно:**
- Подключить фронтенд-приложение (React, Vue, Angular)
- Разрешить запросы с `https://myapp.com` к `http://api.myapp.com`
- Безопасно контролировать, кто может обращаться к API

### Настройка через .env
```ini
# Разработка: разрешить все источники
CORS_ORIGINS=*

# Production: только конкретные домены (рекомендуется!)
CORS_ORIGINS=https://myapp.com,https://www.myapp.com,http://localhost:3000
```

### Примеры использования

**Разработка (фронт на localhost:3000):**
```ini
CORS_ORIGINS=http://localhost:3000
```

**Production (несколько доменов):**
```ini
CORS_ORIGINS=https://myapp.com,https://api.myapp.com,https://admin.myapp.com
```

### Тестирование CORS

**Из браузера (JavaScript):**
```javascript
// Откройте консоль браузера (F12) на любом сайте
fetch('http://127.0.0.1:18000/health')
  .then(res => res.json())
  .then(data => console.log('✅ CORS works!', data))
  .catch(err => console.error('❌ CORS failed:', err));
```

**Из PowerShell:**
```powershell
# Проверка CORS заголовков
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
$response.Headers["Access-Control-Allow-Origin"]
# Должно вывести: *
```

### Безопасность

⚠️ **Важно для Production:**
- ❌ **Не используйте `CORS_ORIGINS=*` в production!**
- ✅ Указывайте только нужные домены
- ✅ Используйте HTTPS для production доменов
- ✅ Регулярно проверяйте список разрешённых источников

---

## Docker Health Monitoring

### Healthcheck для БД

Docker автоматически мониторит здоровье PostgreSQL:

**Параметры:**
- **Команда:** `pg_isready -U postgres -d wine_db`
- **Интервал:** Каждые 10 секунд
- **Timeout:** 5 секунд
- **Retries:** 5 попыток до признания unhealthy
- **Start period:** 10 секунд грейс-период после старта

**Проверка статуса:**
```powershell
# Статус контейнеров (должен быть "healthy")
docker compose ps

# Детальная информация о health checks
docker inspect wine_assistant-db-1 --format='{{.State.Health.Status}}'

# История последних проверок
docker inspect wine_assistant-db-1 --format='{{json .State.Health.Log}}' | ConvertFrom-Json | Select-Object -First 3
```

### Автоматический перезапуск

Оба сервиса настроены с `restart: unless-stopped`:

**Когда контейнеры перезапустятся автоматически:**
- ✅ При сбое процесса (crash)
- ✅ При ошибке в контейнере
- ✅ При перезагрузке хоста Docker

**Когда НЕ перезапустятся:**
- ❌ После `docker stop` (ручная остановка)
- ❌ После `docker compose stop`
- ❌ После `docker compose down`

### Зависимости сервисов

Adminer настроен с `depends_on` и условием `service_healthy`:
```yaml
depends_on:
  db:
    condition: service_healthy
```

**Результат:** Adminer запустится только после того, как БД станет `healthy`.

---

## Docker API Service

### Запуск через Docker Compose

API теперь доступен как отдельный сервис в Docker:
```powershell
# Запустить все сервисы
docker compose up -d

# Проверить статус
docker compose ps

# Логи API
docker compose logs -f api

# Остановить
docker compose down
```

### Архитектура
```
Docker Compose:
├─ db (PostgreSQL + pgvector)
│  └─ Healthcheck: pg_isready
├─ adminer (Database UI)
│  └─ Зависит от: db (healthy)
└─ api (Flask API)
   ├─ Зависит от: db (healthy)
   └─ Healthcheck: curl /ready
```

### Healthcheck для API

API настроен с автоматическим healthcheck:

**Параметры:**
- **Команда:** `curl -f http://localhost:8000/ready`
- **Интервал:** 30 секунд
- **Timeout:** 10 секунд
- **Retries:** 3 попытки
- **Start period:** 40 секунд (время на инициализацию)

**Проверка статуса:**
```powershell
# Статус всех сервисов (должен быть "healthy")
docker compose ps

# Детальная информация о health checks
docker inspect wine_assistant-api-1 --format='{{.State.Health.Status}}'

# История последних проверок
docker inspect wine_assistant-api-1 --format='{{json .State.Health.Log}}' | ConvertFrom-Json | Select-Object -First 3
```

### Переменные окружения

API использует следующие переменные из `.env`:
```ini
# API Service
FLASK_PORT=18000          # Порт на хосте (внутри контейнера всегда 8000)
API_KEY=your_secret_key   # API ключ для защищённых эндпоинтов
APP_VERSION=0.4.0         # Версия API
LOG_LEVEL=INFO            # Уровень логирования (DEBUG/INFO/WARN/ERROR)
CORS_ORIGINS=*            # CORS origins (для production указать конкретные)

# Rate Limiting (новое в v0.4.0)
RATE_LIMIT_ENABLED=1                    # Включить/выключить
RATE_LIMIT_PUBLIC=100/hour             # Публичные endpoints
RATE_LIMIT_PROTECTED=1000/hour         # Защищённые endpoints

# Database (используется для подключения)
PGHOST=db                 # В Docker используется имя сервиса
PGPORT=5432               # Внутренний порт БД
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db
```

### Endpoints доступные в Docker

После запуска API доступен на:

- **Публичные:**
  - http://127.0.0.1:18000/health — Базовая проверка
  - http://127.0.0.1:18000/live — Liveness probe
  - http://127.0.0.1:18000/ready — Readiness probe
  - http://127.0.0.1:18000/version — Версия API
  - http://127.0.0.1:18000/search — Поиск вин
  - http://127.0.0.1:18000/catalog/search — Расширенный поиск
  - http://127.0.0.1:18000/docs — Swagger UI

- **Защищённые (требуется X-API-Key):**
  - http://127.0.0.1:18000/sku/{code} — Карточка товара
  - http://127.0.0.1:18000/sku/{code}/price-history — История цен
  - http://127.0.0.1:18000/sku/{code}/inventory-history — История остатков

### Troubleshooting

#### API unhealthy или не запускается
```powershell
# 1. Проверьте логи API
docker compose logs api

# 2. Проверьте, что БД healthy
docker compose ps db

# 3. Проверьте подключение к БД изнутри контейнера
docker compose exec api python -c "import psycopg2; print(psycopg2.connect('host=db dbname=wine_db user=postgres password=dev_local_pw'))"

# 4. Перезапустите сервис
docker compose restart api

# 5. Пересоздайте контейнеры
docker compose down
docker compose up -d --build
```

#### API показывает старую версию
```powershell
# Пересоберите образ
docker compose build --no-cache api
docker compose up -d
```

#### Порт 18000 занят
```powershell
# Измените порт в .env
FLASK_PORT=18001

# Перезапустите
docker compose down
docker compose up -d
```

### Production Deployment

Для production окружения:

1. **Измените Flask на Gunicorn:**
```dockerfile
   # В Dockerfile замените CMD на:
   CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "api.app:app"]
```

2. **Установите Gunicorn:**
```
   # В requirements.txt добавьте:
   gunicorn==21.2.0
```

3. **Настройте environment variables:**
```ini
   FLASK_DEBUG=0
   LOG_LEVEL=INFO
   CORS_ORIGINS=https://yourdomain.com
   RATE_LIMIT_STORAGE_URL=redis://redis:6379/0
```

4. **Используйте secrets для паролей:**
   - Не храните пароли в `.env` в production
   - Используйте Docker secrets или AWS Secrets Manager

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

### Ошибка: `429 Too Many Requests` 🆕

**Причина:** Превышен лимит запросов.

**Решение:**
```powershell
# 1. Проверьте headers в предыдущем успешном ответе
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
Write-Host "Remaining: $($response.Headers['X-RateLimit-Remaining'])"
Write-Host "Reset at: $($response.Headers['X-RateLimit-Reset'])"

# 2. Подождите до сброса счётчика (время в Unix timestamp)
# Или увеличьте лимиты в .env:
$env:RATE_LIMIT_PUBLIC = "1000/hour"
docker compose restart api

# 3. Временно отключить rate limiting (только для dev!)
$env:RATE_LIMIT_ENABLED = "0"
docker compose restart api
```

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

### Rate limiting не работает 🆕

**Причина:** Flask-Limiter не установлен или неправильно настроен.

**Решение:**
```powershell
# 1. Проверьте, что Flask-Limiter установлен
pip list | Select-String "Flask-Limiter"

# 2. Если нет - установите
pip install Flask-Limiter

# 3. Проверьте .env
Get-Content .env | Select-String "RATE_LIMIT"

# 4. Проверьте headers в ответе
$response = Invoke-WebRequest -Uri "http://127.0.0.1:18000/health"
$response.Headers.Keys | Select-String "RateLimit"

# 5. Перезапустите API
docker compose restart api
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

**Спринт 1 — Database Schema & ETL Enhancement:**
- [x] ~~Синхронизировать `db/init.sql` с миграциями~~ ✅
- [x] ~~Битемпоральная архитектура данных~~ ✅
- [x] ~~Две цены (price_list_rub, price_final_rub)~~ ✅
- [x] ~~История цен и остатков~~ ✅
- [x] ~~Production guardrails (constraints)~~ ✅
- [x] ~~Продвинутый ETL с авто-определением кодировки~~ ✅

**Спринт 2 — Production Readiness:**
- [x] ~~Добавить healthcheck с проверкой БД в `/ready`~~ ✅
- [x] ~~Добавить `/live` liveness probe~~ ✅
- [x] ~~Добавить `/version` endpoint~~ ✅
- [x] ~~Вынести CORS (`flask-cors`) для фронта~~ ✅
- [x] ~~Docker Compose healthcheck для автоматического перезапуска~~ ✅
- [x] ~~Non-root user в Docker для безопасности~~ ✅

**Спринт 3 — Security & Rate Limiting:**
- [x] ~~Rate limiting для всех endpoints~~ ✅
- [x] ~~Исправить SQL injection уязвимости~~ ✅
- [x] ~~Настройка через environment variables~~ ✅
- [x] ~~Поддержка Redis для distributed rate limiting~~ ✅
- [x] ~~Rate limit headers в ответах~~ ✅
- [x] ~~Swagger/OpenAPI документация~~ ✅

### 🚧 В работе

- [ ] Покрыть `scripts/load_csv.py` тестами (минимум happy-path + разбор S5 + конфликтующие цены)
- [ ] Structured Logging (JSON logging, request tracing, performance metrics)

### 📋 Планируется

**Спринт 4 — Testing & Quality:**
- [ ] Testing Infrastructure (pytest, integration tests, API tests)
- [ ] Code coverage >80%
- [ ] Performance tests (load testing, stress testing)
- [ ] End-to-end tests

**Спринт 5 — Advanced Features:**
- [ ] Консолидировать ETL: удалить устаревший `etl/run_daily.py`
- [ ] Примеры клиентов (Python `requests`, JavaScript `fetch`)
- [ ] Метрики (логирование запросов, время ответа)
- [ ] Sentry/OpenTelemetry интеграция (опционально)

**Спринт 6 — User Features:**
- [ ] Telegram-бот для поиска и получения карточек товаров
- [ ] Векторный поиск с эмбеддингами + rerank для улучшения релевантности
- [ ] Export функциональность (Excel, PDF, JSON)
- [ ] Advanced filtering (price range, multiple regions, etc.)

---

## 📝 История изменений

### v0.4.0 — Спринт 3: Security & Rate Limiting (27 октября 2025)

**Добавлено:**
- ✅ **Rate Limiting:** Защита от DDoS и злоупотреблений
  - Публичные endpoints: 100 req/hour (настраивается)
  - Защищённые endpoints: 1000 req/hour (настраивается)
  - Rate limit headers в каждом ответе
  - HTTP 429 с детальной информацией
  - Поддержка Redis для distributed systems
  - Гибкая настройка через environment variables
- ✅ **Security Fixes:** Исправлены SQL injection уязвимости
- ✅ **Documentation:** Полная документация rate limiting в README

**Изменено:**
- 🔄 `.env.example` — добавлены переменные `RATE_LIMIT_*`
- 🔄 `requirements.txt` — добавлен Flask-Limiter
- 🔄 `api/app.py` — интеграция Flask-Limiter с конфигурацией

**Dependencies:**
- Flask-Limiter 3.5.0

---

### v0.3.0 — Спринт 2: Production Readiness (18-21 октября 2025)

**Добавлено:**
- ✅ `/live` endpoint — Liveness probe (uptime, версия, timestamp)
- ✅ `/ready` endpoint — Readiness probe (БД + таблицы + индексы + constraints)
- ✅ `/version` endpoint — Версия API
- ✅ Отслеживание uptime (app.start_time)
- ✅ Docker API Service с автоматическим healthcheck
- ✅ CORS configuration через environment variables
- ✅ Non-root user в Docker (appuser)
- ✅ Graceful service dependencies в docker-compose.yml

**Документация:**
- ✅ Детальное описание healthcheck эндпоинтов
- ✅ Примеры использования для Kubernetes/Docker
- ✅ Troubleshooting для 503 Service Unavailable
- ✅ Раздел про CORS configuration
- ✅ Раздел про Docker API Service

---

### v0.2.0 — Спринт 1: Database Schema & ETL Enhancement (17 октября 2025)

**Добавлено:**
- ✅ Битемпоральная архитектура данных
- ✅ Две цены: price_list_rub + price_final_rub
- ✅ История цен (product_prices) с temporal intervals
- ✅ История остатков (inventory_history)
- ✅ Production guardrails (EXCLUDE constraints, CHECK constraints)
- ✅ Продвинутый ETL (scripts/load_csv.py)
- ✅ Авто-определение кодировки (UTF-8/CP1251/Latin1)
- ✅ Извлечение скидки из ячейки Excel (S5)
- ✅ Валидация кодов товаров (regex)

---

## 📝 Лицензия

MIT

## 🤝 Контрибьюция

Pull requests приветствуются! Для крупных изменений сначала откройте issue для обсуждения.

---

**Сделано с ❤️ для винной индустрии** 🍷

**Версия:** 0.4.0 | **Дата:** 28 октября 2025 | **Спринт:** 3 (Security & Rate Limiting)
