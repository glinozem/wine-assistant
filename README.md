# 🍷 Wine Assistant

[![CI](https://github.com/glinozem/wine-assistant/workflows/CI/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Tests](https://github.com/glinozem/wine-assistant/workflows/Tests/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Release Drafter](https://github.com/glinozem/wine-assistant/workflows/Release%20Drafter/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Coverage](https://img.shields.io/badge/coverage-26.69%25-green.svg)](https://github.com/glinozem/wine-assistant)
[![Version](https://img.shields.io/badge/version-0.4.1-blue.svg)](https://github.com/glinozem/wine-assistant/releases)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Современная система каталога и управления ценами на вино**
> Production-ready Flask API + PostgreSQL (pg_trgm, pgvector) с битемпоральной архитектурой данных, ограничением частоты запросов, структурированным логированием и всесторонним мониторингом состояния.

**Текущая версия:** 0.4.1 (Спринт 3 — Безопасность и ограничение запросов + Структурированное логирование)
**Последнее обновление:** 31 октября 2025

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Что нового](#-что-нового-в-v041)
- [Архитектура](#-архитектура)
- [Быстрый старт](#-быстрый-старт)
- [Документация API](#-документация-api)
- [Конфигурация](#-конфигурация)
- [Разработка](#-разработка)
- [Развертывание](#-развертывание)
- [Мониторинг и наблюдаемость](#-мониторинг-и-наблюдаемость)
- [Устранение неполадок](#-устранение-неполадок)
- [Дорожная карта](#-дорожная-карта)
- [Участие в разработке](#-участие-в-разработке)
- [Лицензия](#-лицензия)

---

## 🚀 Возможности

### Основной функционал
- 📦 **Управление каталогом вин** — Товары, цены, остатки с полной историей
- 📈 **Битемпоральная архитектура** — Отслеживание как даты действия, так и временных меток приема данных
- 🔍 **Расширенный поиск** — Полнотекстовый поиск с pg_trgm similarity + фильтры
- 💰 **Двойная система цен** — Базовая цена (`price_list_rub`) + Финальная цена (`price_final_rub`) с отслеживанием скидок
- 📊 **Исторические данные** — Полный аудит изменений цен и остатков
- 📥 **ETL-конвейер** — Автоматизированный импорт Excel/CSV с автоопределением кодировки

### Возможности для production
- 🛡️ **Ограничение запросов** — Защита от DDoS с настраиваемыми лимитами (100/1000 запросов/час)
- 🔒 **Безопасность** — Аутентификация по API-ключу, настройка CORS, защита от SQL-инъекций
- 🏥 **Мониторинг здоровья** — Endpoints Liveness (`/live`), Readiness (`/ready`) и Version
- 📝 **Структурированное логирование** — JSON-логи с трассировкой запросов и метриками производительности
- 📚 **OpenAPI/Swagger** — Интерактивная документация API на `/docs`
- 🐳 **Поддержка Docker** — Полная настройка Docker Compose с проверками здоровья
- ♻️ **Автоперезапуск** — Устойчивые зависимости сервисов с запуском на основе состояния здоровья

### Качество данных и операции
- ✅ **Валидация данных** — Нормализация SKU, валидация цен, обнаружение дубликатов
- 🎯 **Управление скидками** — Гибкое применение скидок (из ячейки Excel, заголовка или столбца)
- 🗂️ **Мастер-данные** — Поддержка производителей, регионов, сортов винограда, апелласьонов
- 📦 **Кеги и порции** — Цены HoReCa для различных объемов подачи (125мл, 150мл, 750мл, 1л)
- 🔄 **Миграции** — Версионирование схемы на основе SQL с защитными механизмами

---

## 🎉 Что нового в v0.4.1

### Структурированное логирование (НОВОЕ!)
- ✨ **JSON-логирование** — Все логи в структурированном JSON-формате
- 🔍 **Трассировка запросов** — Уникальный Request ID для каждого HTTP-запроса
- ⏱️ **Метрики производительности** — Автоматический учет времени выполнения запросов
- 📊 **Готовность к production** — Совместимость с Datadog, ELK, Splunk
- 🎯 **Контекстная информация** — IP клиента, User-Agent, HTTP-метод, путь, код статуса

**Пример лога:**
```json
{
  "timestamp": 1761708697.331,
  "level": "INFO",
  "logger": "app",
  "message": "Request completed",
  "request_id": "req_76a01810",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 2.14,
  "response_size_bytes": 17
}
```

### Предыдущие обновления (v0.4.0)
- 🛡️ **Ограничение запросов** — Защита от DDoS и злоупотреблений
- 🔒 **Исправления безопасности** — Устранены уязвимости SQL-инъекций
- 📊 **Заголовки лимитов** — Заголовки `X-RateLimit-*` во всех ответах
- 📝 **Поддержка Redis** — Распределенное ограничение запросов для multi-instance развертываний

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Wine Assistant                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   ETL Layer  │──────│  Flask API   │──────│  PostgreSQL  │  │
│  │              │      │              │      │              │  │
│  │ • Excel/CSV  │      │ • REST API   │      │ • pgvector   │  │
│  │ • Validation │      │ • Swagger UI │      │ • pg_trgm    │  │
│  │ • Normalize  │      │ • Rate Limit │      │ • Bitemporal │  │
│  │ • Discount   │      │ • Auth       │      │ • Partitions │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│         │                      │                      │          │
│         └──────────────────────┴──────────────────────┘          │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Infrastructure Layer                         │  │
│  │  • Docker Compose  • Healthchecks  • Auto-restart        │  │
│  │  • Structured Logs • Prometheus    • Redis (optional)    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Технологический стек

| Компонент | Технология | Назначение |
|-----------|-----------|---------|
| **Backend** | Flask 3.0 | REST API фреймворк |
| **База данных** | PostgreSQL 16 + pgvector | Основное хранилище данных с векторным поиском |
| **Поиск** | pg_trgm | Полнотекстовый поиск по сходству |
| **Аутентификация** | API Key | Простая аутентификация |
| **Ограничение запросов** | Flask-Limiter | Защита от DDoS |
| **Логирование** | python-json-logger | Структурированные JSON-логи |
| **API Docs** | Flasgger (OpenAPI 3.0) | Интерактивная документация |
| **ETL** | pandas + openpyxl | Обработка данных |
| **Контейнеризация** | Docker + Docker Compose | Развертывание |
| **CI/CD** | GitHub Actions | Автоматизированное тестирование и релизы |
| **Тестирование** | pytest + pytest-cov | Unit/Integration тесты |

---

## ⚡ Быстрый старт

### Предварительные требования
- Docker 20.10+ и Docker Compose 2.0+
- Python 3.11+ (для локальной разработки)
- Минимум 4 ГБ RAM
- Клиент PostgreSQL (опционально, для ручного доступа к БД)

### 1. Клонирование репозитория
```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant
```

### 2. Запуск сервисов
```bash
# Запуск PostgreSQL + Adminer + API
docker compose up -d

# Проверка статуса (должно показать "healthy")
docker compose ps
```

**Сервисы:**
- 🗄️ PostgreSQL: `localhost:15432`
- 🌐 API: `http://localhost:18000`
- 🔧 Adminer (DB UI): `http://localhost:18080`

### 3. Настройка окружения
```bash
# Копирование примера конфигурации
cp .env.example .env

# Редактирование конфигурации (обязательно: API_KEY)
nano .env  # или ваш любимый редактор
```

**Минимальный `.env`:**
```env
# База данных (уже настроена для Docker)
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db

# Безопасность API
API_KEY=your-secret-api-key-minimum-32-chars

# Конфигурация API
FLASK_HOST=127.0.0.1
FLASK_PORT=18000
FLASK_DEBUG=0
APP_VERSION=0.4.1

# CORS (Разработка: *, Production: конкретные домены)
CORS_ORIGINS=*

# Логирование
LOG_LEVEL=INFO

# Ограничение запросов
RATE_LIMIT_ENABLED=1
RATE_LIMIT_PUBLIC=100/hour
RATE_LIMIT_PROTECTED=1000/hour
```

### 4. Проверка здоровья
```bash
# Базовая проверка здоровья
curl http://localhost:18000/health

# Детальная проверка готовности
curl http://localhost:18000/ready | jq

# Просмотр логов
docker compose logs -f api
```

### 5. Загрузка примеров данных (Опционально)
```bash
# Установка зависимостей Python
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Загрузка примера CSV
python scripts/load_csv.py --csv data/sample/dw_sample_products.csv

# Или загрузка Excel со скидкой из ячейки S5
python scripts/load_csv.py --excel "data/inbox/Price_2025_01_20.xlsx" --asof 2025-01-20 --discount-cell S5
```

### 6. Доступ к API
- **Swagger UI**: http://localhost:18000/docs
- **Health Check**: http://localhost:18000/health
- **Поиск вин**: http://localhost:18000/search?q=венето&max_price=3000

---

## 📚 Документация API

### Базовый URL
```
http://localhost:18000
```

### Аутентификация
Защищенные endpoints требуют API-ключ в заголовке:
```bash
X-API-Key: your-secret-api-key
```

### Ограничение запросов

| Тип Endpoint | Лимит по умолчанию | Заголовки |
|---------------|---------------|---------|
| Публичные | 100 запросов/час | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |
| Защищенные (API key) | 1000 запросов/час | То же + `Retry-After` при 429 |

**Пример:**
```bash
curl -I http://localhost:18000/health
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 1730138509
```

### Основные Endpoints

#### Здоровье и мониторинг

##### `GET /health`
Простая проверка здоровья (без БД).
```bash
curl http://localhost:18000/health
# {"ok": true}
```

##### `GET /live`
Проверка жизнеспособности (liveness probe для Kubernetes).
```bash
curl http://localhost:18000/live
# {"status": "alive", "timestamp": "2025-01-29T10:30:00Z"}
```

##### `GET /ready`
Проверка готовности с детальной информацией о БД.
```bash
curl http://localhost:18000/ready | jq
```

**Ответ:**
```json
{
  "status": "ready",
  "checks": {
    "database": "healthy",
    "version": "PostgreSQL 16.1",
    "migrations": "up-to-date"
  },
  "timestamp": "2025-01-29T10:30:00Z"
}
```

##### `GET /version`
Информация о версии приложения.
```bash
curl http://localhost:18000/version
```

**Ответ:**
```json
{
  "version": "0.4.1",
  "commit": "abc123",
  "build_date": "2025-01-29"
}
```

#### Поиск

##### `GET /search`
Поиск вин с фильтрами.

**Параметры:**
- `q` (string) — Поисковый запрос (название, производитель, регион)
- `min_price` (float) — Минимальная цена в рублях
- `max_price` (float) — Максимальная цена в рублях
- `country` (string) — Страна производства
- `wine_type` (string) — Тип вина (красное, белое, розовое, игристое)
- `limit` (int) — Количество результатов (по умолчанию: 20, максимум: 100)
- `offset` (int) — Смещение для пагинации

**Пример:**
```bash
curl "http://localhost:18000/search?q=венето&max_price=3000&limit=10"
```

**Ответ:**
```json
{
  "results": [
    {
      "sku": "D011283",
      "product_name": "Вино Венето Мерло",
      "producer": "Cantina di Soave",
      "country": "Италия",
      "region": "Венето",
      "wine_type": "красное",
      "price_list_rub": 2500.00,
      "price_final_rub": 2250.00,
      "discount_pct": 10.00,
      "qty_available": 24
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

#### Товары по SKU

##### `GET /sku/{sku}`
Получить товар по SKU (требуется API-ключ).

**Пример:**
```bash
curl -H "X-API-Key: your-secret-api-key" \
     http://localhost:18000/sku/D011283
```

**Ответ:**
```json
{
  "sku": "D011283",
  "product_name": "Вино Венето Мерло",
  "producer": "Cantina di Soave",
  "country": "Италия",
  "region": "Венето",
  "appellation": "DOC Veneto",
  "wine_type": "красное",
  "grape_varieties": "Мерло 100%",
  "vintage": 2021,
  "price_list_rub": 2500.00,
  "price_final_rub": 2250.00,
  "discount_pct": 10.00,
  "qty_available": 24,
  "price_date": "2025-01-20",
  "created_at": "2025-01-20T08:15:00Z",
  "updated_at": "2025-01-20T08:15:00Z"
}
```

##### `GET /sku/{sku}/history`
История изменений цен и остатков для SKU (требуется API-ключ).

**Пример:**
```bash
curl -H "X-API-Key: your-secret-api-key" \
     http://localhost:18000/sku/D011283/history
```

**Ответ:**
```json
{
  "sku": "D011283",
  "history": [
    {
      "price_date": "2025-01-20",
      "price_list_rub": 2500.00,
      "price_final_rub": 2250.00,
      "discount_pct": 10.00,
      "qty_available": 24,
      "ingested_at": "2025-01-20T08:15:00Z"
    },
    {
      "price_date": "2025-01-15",
      "price_list_rub": 2400.00,
      "price_final_rub": 2400.00,
      "discount_pct": 0.00,
      "qty_available": 30,
      "ingested_at": "2025-01-15T09:00:00Z"
    }
  ],
  "total": 2
}
```

#### Статистика

##### `GET /stats`
Статистика базы данных (требуется API-ключ).

**Пример:**
```bash
curl -H "X-API-Key: your-secret-api-key" \
     http://localhost:18000/stats
```

**Ответ:**
```json
{
  "total_products": 1247,
  "total_skus": 1189,
  "products_with_price": 1189,
  "products_in_stock": 856,
  "total_value_rub": 4567890.50,
  "avg_price_rub": 3842.15,
  "countries": 15,
  "producers": 234,
  "last_update": "2025-01-29T08:15:00Z"
}
```

### Коды ответов

| Код | Статус | Описание |
|-----|--------|----------|
| 200 | OK | Успешный запрос |
| 400 | Bad Request | Неверные параметры запроса |
| 401 | Unauthorized | Отсутствует или неверный API-ключ |
| 404 | Not Found | Ресурс не найден |
| 429 | Too Many Requests | Превышен лимит запросов |
| 500 | Internal Server Error | Внутренняя ошибка сервера |
| 503 | Service Unavailable | Сервис недоступен (проблемы с БД) |

### Обработка ошибок

Все ошибки возвращаются в JSON-формате:

```json
{
  "error": "SKU not found",
  "code": "NOT_FOUND",
  "details": {
    "sku": "INVALID123"
  }
}
```

---

## ⚙️ Конфигурация

### Переменные окружения

Полный список переменных окружения в `.env`:

#### База данных
```env
PGHOST=127.0.0.1          # Хост PostgreSQL
PGPORT=15432              # Порт PostgreSQL
PGUSER=postgres           # Пользователь PostgreSQL
PGPASSWORD=dev_local_pw   # Пароль PostgreSQL
PGDATABASE=wine_db        # Имя базы данных
```

#### API
```env
FLASK_HOST=127.0.0.1      # Хост Flask
FLASK_PORT=18000          # Порт Flask
FLASK_DEBUG=0             # Режим отладки (0=выкл, 1=вкл)
APP_VERSION=0.4.1         # Версия приложения
API_KEY=your-secret-key   # API-ключ (минимум 32 символа)
```

#### Безопасность
```env
CORS_ORIGINS=*            # Разрешенные CORS origins (* для разработки)
SECRET_KEY=change-me      # Секретный ключ Flask
```

#### Логирование
```env
LOG_LEVEL=INFO            # Уровень логирования (DEBUG, INFO, WARNING, ERROR)
LOG_FORMAT=json           # Формат логов (json или text)
```

#### Ограничение запросов
```env
RATE_LIMIT_ENABLED=1                    # Включить ограничение (0=выкл, 1=вкл)
RATE_LIMIT_PUBLIC=100/hour              # Лимит для публичных endpoints
RATE_LIMIT_PROTECTED=1000/hour          # Лимит для защищенных endpoints
RATE_LIMIT_STORAGE_URL=redis://localhost:6379/0  # Redis для распределенных лимитов (опционально)
```

### Конфигурация Docker

Настройка Docker Compose в `docker-compose.yml`:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    ports:
      - "15432:5432"
    environment:
      POSTGRES_PASSWORD: dev_local_pw
      POSTGRES_DB: wine_db
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "18000:18000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
```

### Конфигурация CORS

Для production настройте конкретные домены:

```env
# Разработка
CORS_ORIGINS=*

# Production
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

### Настройка лимитов

Настройте лимиты в зависимости от нагрузки:

```env
# Консервативно (малая нагрузка)
RATE_LIMIT_PUBLIC=50/hour
RATE_LIMIT_PROTECTED=500/hour

# Умеренно (средняя нагрузка)
RATE_LIMIT_PUBLIC=100/hour
RATE_LIMIT_PROTECTED=1000/hour

# Агрессивно (высокая нагрузка)
RATE_LIMIT_PUBLIC=200/hour
RATE_LIMIT_PROTECTED=2000/hour
```

---

## 💻 Разработка

### Локальная установка

```bash
# Создание виртуального окружения
python -m venv .venv

# Активация
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dev dependencies
```

### Запуск локально

```bash
# Запуск только БД в Docker
docker compose up -d db

# Запуск API локально
python app.py
```

### Структура проекта

```
wine-assistant/
├── app.py                    # Основное приложение Flask
├── config.py                 # Конфигурация
├── requirements.txt          # Python зависимости
├── Dockerfile               # Docker образ
├── docker-compose.yml       # Docker Compose конфигурация
├── .env.example             # Пример переменных окружения
│
├── api/                     # API endpoints
│   ├── __init__.py
│   ├── health.py           # Health/readiness endpoints
│   ├── search.py           # Поиск вин
│   ├── sku.py              # SKU endpoints
│   └── stats.py            # Статистика
│
├── db/                      # База данных
│   ├── connection.py       # Подключение к БД
│   ├── queries.py          # SQL запросы
│   └── migrations/         # SQL миграции
│       ├── 001_initial.sql
│       └── 002_add_indexes.sql
│
├── etl/                     # ETL пайплайн
│   ├── loader.py           # Загрузчик данных
│   ├── validator.py        # Валидация данных
│   └── normalizer.py       # Нормализация данных
│
├── scripts/                 # Утилиты
│   ├── load_csv.py         # Загрузка CSV/Excel
│   ├── migrate.ps1         # Скрипт миграций
│   └── backup.sh           # Скрипт бэкапов
│
├── tests/                   # Тесты
│   ├── test_api.py
│   ├── test_etl.py
│   └── test_db.py
│
└── docs/                    # Документация
    ├── API.md
    ├── DEPLOYMENT.md
    └── ROADMAP_v3_RU.md
```

### Тестирование

```bash
# Запуск всех тестов
pytest

# Запуск с coverage
pytest --cov=. --cov-report=html

# Запуск конкретного теста
pytest tests/test_api.py::test_health_endpoint

# Запуск с verbose
pytest -v -s
```

### Линтинг и форматирование

```bash
# Установка pre-commit hooks
pre-commit install

# Запуск линтеров вручную
pre-commit run --all-files

# Форматирование кода
black .
isort .

# Проверка типов
mypy app.py
```

### Работа с миграциями

```bash
# Применение миграций (PowerShell)
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1

# Применение миграций (bash)
bash scripts/migrate.sh

# Создание новой миграции
# 1. Создайте файл db/migrations/XXX_description.sql
# 2. Напишите SQL
# 3. Запустите migrate.ps1
```

### Отладка

```bash
# Включение режима отладки
FLASK_DEBUG=1 python app.py

# Просмотр логов в реальном времени
docker compose logs -f api

# Подключение к БД
psql -h localhost -p 15432 -U postgres -d wine_db

# Проверка здоровья БД
curl http://localhost:18000/ready | jq
```

---

## 🚀 Развертывание

### Docker Production

#### 1. Подготовка

```bash
# Клонирование репозитория
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# Создание production .env
cp .env.example .env
nano .env  # Настройте параметры
```

#### 2. Production .env

```env
# Database
PGHOST=db
PGPORT=5432
PGUSER=postgres
PGPASSWORD=your-strong-password-here
PGDATABASE=wine_db

# API
FLASK_HOST=0.0.0.0
FLASK_PORT=18000
FLASK_DEBUG=0
APP_VERSION=0.4.1

# Security
API_KEY=your-production-api-key-min-32-chars
SECRET_KEY=your-production-secret-key-min-32-chars
CORS_ORIGINS=https://yourdomain.com

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Rate Limiting
RATE_LIMIT_ENABLED=1
RATE_LIMIT_PUBLIC=100/hour
RATE_LIMIT_PROTECTED=1000/hour
```

#### 3. Запуск

```bash
# Сборка и запуск
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f api
```

#### 4. Проверка

```bash
# Health check
curl https://yourdomain.com/health

# Readiness check
curl https://yourdomain.com/ready | jq

# API test
curl -H "X-API-Key: your-api-key" \
     https://yourdomain.com/stats | jq
```

### Kubernetes

#### Deployment YAML

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wine-assistant
spec:
  replicas: 3
  selector:
    matchLabels:
      app: wine-assistant
  template:
    metadata:
      labels:
        app: wine-assistant
    spec:
      containers:
      - name: api
        image: glinozem/wine-assistant:0.4.1
        ports:
        - containerPort: 18000
        env:
        - name: PGHOST
          value: "postgres-service"
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: wine-assistant-secrets
              key: api-key
        livenessProbe:
          httpGet:
            path: /live
            port: 18000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 18000
          initialDelaySeconds: 5
          periodSeconds: 10
```

### Reverse Proxy (Nginx)

```nginx
upstream wine_assistant {
    server localhost:18000;
}

server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://wine_assistant;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Rate limiting (дополнительно к application-level)
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;
}
```

### Мониторинг Production

#### Prometheus Metrics

Добавьте Prometheus exporter:

```bash
pip install prometheus-flask-exporter
```

```python
from prometheus_flask_exporter import PrometheusMetrics

metrics = PrometheusMetrics(app)
```

#### Healthcheck Endpoints

- **Liveness**: `/live` — API работает?
- **Readiness**: `/ready` — API готов принимать трафик?
- **Metrics**: `/metrics` — Prometheus метрики

### Бэкапы

```bash
# Бэкап БД
docker compose exec db pg_dump -U postgres wine_db > backup.sql

# Восстановление
docker compose exec -T db psql -U postgres wine_db < backup.sql

# Автоматический бэкап (crontab)
0 2 * * * docker compose exec db pg_dump -U postgres wine_db | gzip > /backups/wine_db_$(date +\%Y\%m\%d).sql.gz
```

---

## 📊 Мониторинг и наблюдаемость

### Structured Logging

Все логи в JSON-формате для легкой интеграции с системами мониторинга:

```json
{
  "timestamp": 1761708697.331,
  "level": "INFO",
  "logger": "app",
  "message": "Request completed",
  "request_id": "req_76a01810",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 2.14,
  "response_size_bytes": 17,
  "client_ip": "192.168.1.100",
  "user_agent": "curl/7.68.0"
}
```

### Интеграция с системами мониторинга

#### Datadog

```python
import datadog
from pythonjsonlogger import jsonlogger

# Configure Datadog
datadog.initialize(api_key='your-api-key')

# Logs автоматически отправляются в Datadog
```

#### ELK Stack (Elasticsearch + Logstash + Kibana)

```yaml
# filebeat.yml
filebeat.inputs:
- type: container
  paths:
    - '/var/lib/docker/containers/*/*.log'
  processors:
  - decode_json_fields:
      fields: ["message"]
      target: ""
      overwrite_keys: true
```

#### Splunk

```bash
# Настройка Splunk HTTP Event Collector
curl -H "X-API-Key: your-api-key" \
     http://localhost:18000/health \
     | splunk-hec
```

### Метрики производительности

#### Request Duration

```sql
-- Среднее время выполнения запросов
SELECT
  path,
  AVG(duration_ms) as avg_duration,
  MAX(duration_ms) as max_duration,
  COUNT(*) as total_requests
FROM logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY path
ORDER BY avg_duration DESC;
```

#### Rate Limiting Stats

```sql
-- Статистика по лимитам
SELECT
  client_ip,
  COUNT(*) as total_requests,
  SUM(CASE WHEN status_code = 429 THEN 1 ELSE 0 END) as rate_limited
FROM logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY client_ip
ORDER BY rate_limited DESC;
```

### Алерты

Настройте алерты для критических событий:

1. **API недоступен** — `/health` возвращает 500
2. **БД недоступна** — `/ready` возвращает 503
3. **Высокая нагрузка** — Много 429 ответов
4. **Медленные запросы** — duration_ms > 1000ms
5. **Ошибки аутентификации** — Много 401 ответов

### Dashboard пример

```sql
-- Количество запросов в час по endpoint
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  path,
  COUNT(*) as requests
FROM logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour, path
ORDER BY hour DESC, requests DESC;

-- Error rate
SELECT
  DATE_TRUNC('minute', timestamp) as minute,
  SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as error_rate
FROM logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute DESC;

-- Медленные запросы (> 100ms)
SELECT
  request_id,
  method,
  path,
  duration_ms,
  status_code,
  timestamp
FROM logs
WHERE duration_ms > 100
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY duration_ms DESC
LIMIT 10;
```

---

## 🔧 Устранение неполадок

### Частые проблемы

#### ❌ "Column price_final_rub does not exist"

**Причина:** Старая схема базы данных (до Sprint 1).

**Решение:**
```bash
# Вариант 1: Пересоздать базу данных (рекомендуется)
docker compose down -v
docker compose up -d

# Вариант 2: Применить миграции
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

#### ❌ "401 Unauthorized" на /sku/*

**Причина:** Отсутствует или неверный API-ключ.

**Решение:**
```bash
# PowerShell
$headers = @{ "X-API-Key" = "your-secret-api-key" }
Invoke-WebRequest -Uri "http://localhost:18000/sku/D011283" -Headers $headers

# curl
curl -H "X-API-Key: your-secret-api-key" http://localhost:18000/sku/D011283
```

Проверьте, что в файле `.env` установлен `API_KEY`.

#### ❌ "429 Too Many Requests"

**Причина:** Превышен лимит запросов.

**Решение:**
```bash
# Проверить оставшиеся запросы
curl -I http://localhost:18000/health
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1730138509

# Подождать до времени reset или увеличить лимиты в .env
RATE_LIMIT_PUBLIC=1000/hour
docker compose restart api

# Временно отключить (только для разработки!)
RATE_LIMIT_ENABLED=0
docker compose restart api
```

#### ❌ "503 Service Unavailable" на /ready

**Причина:** База данных недоступна или нездорова.

**Решение:**
```bash
# 1. Проверить статус БД
docker compose ps db
# Должно показать "healthy"

# 2. Посмотреть детальную ошибку
curl http://localhost:18000/ready | jq

# 3. Проверить логи БД
docker compose logs db

# 4. Перезапустить сервисы
docker compose restart db
docker compose restart api

# 5. Если не помогает, проверить миграции
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
```

#### ❌ Отсутствуют заголовки rate limit

**Причина:** Flask-Limiter не установлен или неправильно настроен.

**Решение:**
```bash
# 1. Проверить, что Flask-Limiter установлен
pip list | grep Flask-Limiter

# 2. Установить, если отсутствует
pip install Flask-Limiter

# 3. Проверить конфигурацию .env
cat .env | grep RATE_LIMIT

# 4. Перезапустить API
docker compose restart api

# 5. Проверить заголовки
curl -I http://localhost:18000/health | grep RateLimit
```

#### ❌ Логи не в JSON-формате

**Причина:** Старая версия кода или логирование не настроено.

**Решение:**
```bash
# 1. Проверить версию API
curl http://localhost:18000/version
# Должно быть >= 0.4.1

# 2. Пересобрать Docker образ
docker compose build --no-cache api
docker compose up -d

# 3. Проверить логи
docker compose logs api | head -n 5
# Должен быть JSON вывод
```

#### ❌ API не отвечает на порту 18000

**Причина:** Конфликт портов или неправильная конфигурация.

**Решение:**
```bash
# 1. Проверить, занят ли порт
netstat -an | grep 18000  # Linux/macOS
netstat -an | findstr 18000  # Windows

# 2. Проверить FLASK_PORT в .env
cat .env | grep FLASK_PORT

# 3. Изменить порт при необходимости
FLASK_PORT=18001
docker compose down
docker compose up -d

# 4. Обновить URL
curl http://localhost:18001/health
```

### Получение помощи

1. **Проверьте документацию:** http://localhost:18000/docs
2. **Просмотрите логи:** `docker compose logs -f api`
3. **GitHub Issues:** https://github.com/glinozem/wine-assistant/issues
4. **Обсуждения:** https://github.com/glinozem/wine-assistant/discussions

### Режим отладки

Включите режим отладки для детальных сообщений об ошибках:

```env
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
```

**⚠️ Предупреждение:** Никогда не используйте режим отладки в production!

---

## 🗺️ Дорожная карта

### Текущий спринт: Спринт 4 — Тестирование и качество
- [ ] Unit-тесты для ETL (покрытие 60-80%)
- [ ] Интеграционные тесты для API
- [ ] E2E тестовые сценарии
- [ ] Нагрузочное тестирование

### Следующий: Спринт 5 — Продвинутые возможности
- [ ] Telegram-бот для поиска вин
- [ ] Векторный поиск (pgvector + embeddings)
- [ ] Функционал экспорта (Excel/PDF/JSON)
- [ ] Расширенная фильтрация и фасетный поиск

### Будущее: Спринт 6+ — Бизнес-интеграция
- [ ] Идемпотентный импорт (SHA256 hash)
- [ ] Извлечение price_date из заголовка Excel
- [ ] Ежедневный планировщик (Пн-Пт 08:10)
- [ ] Мастер-данные из PDF-каталога
- [ ] Авто-импорт вложений Email/Telegram

**📖 Детальная дорожная карта:** См. [ROADMAP_v3_RU.md](docs/ROADMAP_v3_RU.md) (Русский)

### Завершено ✅
- ✅ **Спринт 1:** Схема базы данных + улучшение ETL
- ✅ **Спринт 2:** Готовность к production (healthchecks, CORS, Docker)
- ✅ **Спринт 3:** Безопасность и ограничение запросов
- ✅ **Спринт 3.1:** Структурированное JSON-логирование

---

## 🤝 Участие в разработке

Мы приветствуем вклад в проект! Пожалуйста, следуйте этим рекомендациям:

### Рабочий процесс разработки
1. Сделайте fork репозитория
2. Создайте ветку функции: `git checkout -b feature/amazing-feature`
3. Внесите изменения и тщательно протестируйте
4. Запустите тесты: `pytest`
5. Запустите pre-commit: `pre-commit run --all-files`
6. Сделайте коммит: `git commit -m "feat: add amazing feature"`
7. Отправьте: `git push origin feature/amazing-feature`
8. Откройте Pull Request

### Соглашение о сообщениях коммитов
Следуйте [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — Новая функция
- `fix:` — Исправление ошибки
- `docs:` — Изменения документации
- `refactor:` — Рефакторинг кода
- `test:` — Добавление/обновление тестов
- `chore:` — Задачи обслуживания
- `ci:` — Изменения CI/CD

**Примеры:**
```
feat(api): add faceted search endpoint
fix(etl): handle empty discount cell gracefully
docs(readme): update deployment instructions
test(api): add rate limiting integration tests
```

### Стиль кода
- **Python:** Следуйте PEP 8
- **SQL:** Ключевые слова в нижнем регистре, отступ 2 пробела
- **Комментарии:** Пишите понятные, краткие комментарии
- **Docstrings:** Используйте стиль Google для функций

### Требования к тестированию
- Unit-тесты для новых функций
- Интеграционные тесты для API endpoints
- Покрытие не должно уменьшаться

---

## 📄 Лицензия

Этот проект лицензирован под лицензией MIT - см. файл [LICENSE](LICENSE) для деталей.

---

## 🙏 Благодарности

- **PostgreSQL** — Самая продвинутая база данных с открытым исходным кодом в мире
- **Flask** — Легкий и гибкий веб-фреймворк
- **pgvector** — Векторный поиск по сходству для PostgreSQL
- **Docker** — Платформа контейнеризации
- **Flasgger** — Интеграция OpenAPI/Swagger для Flask

---

## 📞 Контакты

- **GitHub Issues:** https://github.com/glinozem/wine-assistant/issues
- **Обсуждения:** https://github.com/glinozem/wine-assistant/discussions
- **Ссылка на проект:** https://github.com/glinozem/wine-assistant

---

<div align="center">

**Сделано с ❤️ для винной индустрии 🍷**

[![GitHub Stars](https://img.shields.io/github/stars/glinozem/wine-assistant?style=social)](https://github.com/glinozem/wine-assistant/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/glinozem/wine-assistant?style=social)](https://github.com/glinozem/wine-assistant/network/members)

</div>
