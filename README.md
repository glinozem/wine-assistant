# Wine Assistant 🍷

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Semgrep](https://github.com/glinozem/wine-assistant/actions/workflows/semgrep.yml/badge.svg)](../../actions/workflows/semgrep.yml)
[![Secrets](https://github.com/glinozem/wine-assistant/actions/workflows/secrets.yml/badge.svg)](../../actions/workflows/secrets.yml)

**Production-ready система управления винным каталогом** с REST API, ETL-пайплайном, справочником виноделен, автоматическим импортом изображений, историей остатков и расширенными возможностями экспорта данных.

Изначально учебный проект, Wine Assistant вырос в полноценное решение, демонстрирующее best practices современной backend-разработки на Python.

**Текущий статус:** Production-ready • 164+ тестов • Sprint 7 завершён ✅ • AI Integration планируется (Sprint 8) 🔜

---

## 🎯 Ключевые возможности

### 📊 Управление данными и ETL

- **Автоматический импорт прайс-листов** (Excel/CSV) с интеллектуальным парсингом
- **Извлечение изображений из Excel** → автоматическое заполнение `image_url`
- **Справочник виноделен** (`wineries`) из PDF-каталога поставщика
- **Enrichment каталога** данными о регионе, производителе, сайтах виноделен
- **История цен и остатков** с автоматическим версионированием
- **Ежедневная синхронизация остатков** в `inventory_history` для аналитики и графиков
- **Карантин данных** для невалидных записей (Data Quality Gates)
- **Идемпотентность** загрузок через SHA-256 хеши
- **Партиционирование** таблиц по кварталам для масштабирования

### 🔌 REST API & Интеграции

- **Публичный поиск** по каталогу с фильтрацией и сортировкой
- **SKU карточка** с полными данными о винодельне
- **История цен** и **история остатков** по временным диапазонам
- **Swagger/OpenAPI** документация из коробки
- **API-key авторизация** для защищённых endpoints
- **Structured JSON logging** с request tracking
- **Health checks** (liveness/readiness) для Kubernetes
- **Rate limiting** для защиты от перегрузки

### 📤 Экспорт и отчёты

- **Множественные форматы:** JSON, Excel (.xlsx), PDF
- **Экспорт результатов поиска** с фильтрами
- **PDF-карточки товаров** с изображениями
- **История цен в Excel** для аналитики
- **История остатков в Excel/JSON** с временной шкалой
- **Unicode поддержка** в PDF (кириллица, символ ₽)
- **Фиксированный набор полей** для каждого типа экспорта

### 📈 Визуализация и аналитика

- **Графики истории цен** (Chart.js) в веб-интерфейсе
- **Графики динамики остатков** по SKU
- **Временные срезы** с настраиваемыми диапазонами (`from`/`to`)
- **Экспорт данных для BI** (Excel/JSON)

### 🖼️ Работа с изображениями

- **Автоматическое извлечение** изображений из Excel-прайсов
- **Статическая раздача** через `/static/images/<SKU>.<ext>`
- **Публичные URL** для каждого товара
- **Интеграция в экспорты** (XLSX с колонкой "Фото (URL)", PDF с изображением)

### 🏛️ Справочник виноделен

- **Централизованное хранение** данных о производителях
- **Импорт из PDF-каталога** с нормализацией названий
- **Обогащение продуктов** регионом и сайтом производителя
- **Русские названия** и **описания** виноделен для витрины
- **Автоматическая синхронизация** `products` ↔ `wineries`

### 🤖 AI Capabilities (В разработке - Sprint 8)

> ⚠️ **ВНИМАНИЕ:** AI-слой ещё не реализован. Ниже представлен дизайн и план работ Sprint 8.
>
> Текущий статус: Issues #128-134 открыты, инфраструктура в проектировании.

**Планируемые возможности:**

- **OpenAI/VseLLM интеграция** для LLM-функций (Issue #128)
- **Векторные embeddings** для семантического поиска (Issue #129)
- **Semantic Search** по описаниям вин (Issue #130)
- **AI Wine Description Generator** - автогенерация описаний (Issue #131)
- **AI Testing Infrastructure** (Issue #132)
- **AI Wine Sommelier** с памятью разговора (LangGraph) (Issue #134)
- **AI Monitoring Dashboard** для отслеживания расходов (Issue #133)
- **Cascade Model Architecture** (nano → mini → sonnet-4) для оптимизации затрат

### 🛠️ Инфраструктура

- **Docker Compose** окружение с PostgreSQL 16 + pgvector
- **Автоматические миграции** БД с версионированием
- **CI/CD Pipeline** с GitHub Actions
- **Pre-commit hooks** для проверки кода
- **Adminer** для управления БД
- **Smoke-check скрипты** для быстрой проверки готовности системы

---

## 🚀 Быстрый старт

### Вариант 1: Docker Compose (рекомендуется)

```bash
# Клонирование репозитория
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# Настройка окружения
cp .env.example .env
# Отредактируйте .env при необходимости

# Запуск всего стека
docker compose up -d --build

# Проверка готовности
curl http://localhost:18000/ready
```

**Доступные сервисы:**
- API: http://localhost:18000
- Swagger UI: http://localhost:18000/docs
- Adminer (БД): http://localhost:18080
- Static Images: http://localhost:18000/static/images/

### Вариант 2: Локальная разработка

```bash
# Создание виртуального окружения
python -m venv .venv

# Активация окружения
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate

# Установка зависимостей
pip install -r requirements.txt

# Настройка БД (требуется PostgreSQL 16+)
cp .env.example .env
# Настройте DB_* переменные в .env

# Запуск в режиме разработки
FLASK_ENV=development FLASK_APP=api.wsgi:app flask run
```

### Быстрая проверка работоспособности (Smoke Check)

После запуска стека выполните быстрый smoke-check:

```powershell
# Windows PowerShell
# Установить API ключ
$env:API_KEY = "ВАШ_API_КЛЮЧ"

# Быстрый smoke-check
.\scripts\quick_smoke_check.ps1

# Или полный smoke-check с проверкой всех эндпоинтов
.\scripts\manual_smoke_check.ps1
```

Скрипты проверят:
- Health endpoints (`/live`, `/ready`, `/health`)
- Поиск по каталогу
- Карточки SKU
- Историю цен и остатков
- Экспортные эндпоинты

---

## 📊 Архитектура системы

```
┌──────────────────────────────────────────────┐
│         Presentation Layer                   │
│  • REST API (Flask)                          │
│  • Swagger Documentation                     │
│  • Request Middleware & Logging              │
│  • Static Files Server (/static/images)      │
├──────────────────────────────────────────────┤
│   🔜 AI/ML Layer (PLANNED - Sprint 8)        │
│  • OpenAI/VseLLM Integration                 │
│  • Embeddings Generator (text-embed-3-small) │
│  • Semantic Search Engine                    │
│  • AI Sommelier (LangGraph)                  │
│  • Token Optimizer & Cost Tracking           │
├──────────────────────────────────────────────┤
│         Business Logic                       │
│  • Product Service                           │
│  • Price Management                          │
│  • Inventory History Sync                    │
│  • Wineries Enrichment                       │
│  • Export Service (XLSX/PDF/JSON)            │
│  • Data Validation (Pydantic)                │
│  • Image Extraction & Storage                │
├──────────────────────────────────────────────┤
│         Data Access Layer                    │
│  • PostgreSQL 16 + pgvector                  │
│  • Migrations (Alembic-style)                │
│  • Connection Pooling                        │
│  • Partitioned Tables (quarterly)            │
│  • Vector Similarity Search (HNSW) - ready   │
│  • Wineries Reference Table                  │
│  • Inventory History Table                   │
└──────────────────────────────────────────────┘
```

### Основные компоненты

#### 1. API Layer (`/api`)
- `app.py` - Flask приложение с роутингом
- `schemas.py` - Pydantic модели валидации
- `export.py` - Сервис экспорта в различные форматы
- `request_middleware.py` - Request tracking и логирование
- `logging_config.py` - Structured JSON logging
- `validation.py` - Утилиты валидации запросов

#### 2. ETL Layer (`/scripts`, `/etl`)
- `load_csv.py` - Основной ETL pipeline
- `extract_wineries_from_pdf.py` - Парсинг PDF-каталога виноделен
- `normalize_wineries_suppliers.py` - Нормализация названий производителей
- `load_wineries.py` - Загрузка справочника виноделен в БД
- `enrich_producers.py` - Обогащение продуктов данными из справочника
- `check_wineries_vs_products.py` - Верификация синхронизации
- `sync_inventory_history.py` - Ежедневная синхронизация остатков
- `image_extractor.py` - Извлечение изображений из Excel
- `date_extraction.py` - Интеллектуальное извлечение дат
- `idempotency.py` - Проверка дубликатов через хеши
- `data_quality.py` - Data Quality Gates

#### 3. Database Layer (`/db`)
- Миграции с версионированием
- Партиционирование по кварталам
- Хранимые процедуры для upsert
- Карантинная таблица для DQ
- Справочник виноделен (`wineries`)
- История остатков (`inventory_history`)
- Векторные индексы (HNSW) для pgvector (готовность к AI)

#### 4. AI Layer (`/api/ai`) - Планируемая структура (Sprint 8) 🔜

> **Внимание:** Эти модули ещё не существуют в репозитории. Ниже - проектируемая архитектура.

- `config.py` - Конфигурация AI провайдеров (OpenAI/VseLLM)
- `llm_service.py` - Унифицированный сервис для LLM
- `embeddings.py` - Генерация и управление embeddings
- `semantic_search.py` - Векторный поиск по описаниям
- `sommelier.py` - AI-сомелье с памятью разговора
- `token_optimizer.py` - Оптимизация промптов и расходов
- `model_selector.py` - Каскадный выбор моделей

---

## 🗄️ База данных

### Основные таблицы

#### `products`
Текущие данные по каждому SKU:
- Базовые: `code`, `name`, `title_ru`, `country`, `region`, `color`, `style`
- Характеристики: `grapes`, `vintage`, `alcohol`
- Цены: `price_list_rub`, `price_final_rub`, `discount_pct`
- Остатки: `stock_total`, `stock_free`
- Поставщик: `supplier`, `producer_site`
- Рейтинги: `vivino_rating`, `vivino_url`
- Медиа: `image_url`
- Справочник: связь с `wineries` по `supplier`

#### `product_prices`
История изменений цен с партиционированием:
- `code`, `effective_from`, `effective_to`
- `price_rub`, `discount_pct`
- Партиционирование по кварталам (Issue #85)

#### `inventory`
Текущие остатки товаров:
- `code`, `stock_total`, `stock_free`, `reserved`
- `last_updated`

#### `inventory_history`
История изменений остатков для аналитики:
- `code`, `stock_total`, `stock_free`, `reserved`
- `as_of` - timestamp снимка
- Используется для построения графиков динамики остатков
- Наполняется ежедневно через `sync_inventory_history.py`

#### `wineries`
Справочник производителей (Issue #127):
- `supplier` - ключ связи с `products.supplier`
- `supplier_ru` - русское название винодельни
- `region` - нормализованный регион
- `producer_site` - официальный сайт
- `description_ru` - описание из каталога

#### `price_list_quarantine`
Карантин для невалидных строк прайса:
- Строки, не прошедшие Data Quality Gates
- `code`, `raw_row`, `error_reason`
- Для ручной верификации

#### `file_imports`
Журнал импортов файлов:
- `file_sha256` - хеш для идемпотентности
- `filename`, `import_date`, `status`

### Схема связей

```
products
  └──> supplier (FK) ──> wineries.supplier
  └──> code ──> product_prices.code (1:many)
  └──> code ──> inventory.code (1:1)
  └──> code ──> inventory_history.code (1:many)
```

---

## 🔌 API Endpoints

### Health & Status
- `GET /live` - Liveness probe
- `GET /ready` - Readiness probe (с проверкой БД)
- `GET /health` - Простой health check

### Catalog & Search
- `GET /api/v1/products/search` - Поиск по каталогу
  - Query params: `query`, `color`, `country`, `in_stock`, `limit`, `offset`
  - Поддержка фильтров, сортировки, pagination
- `GET /catalog/search` - Алиас `/api/v1/products/search`

### SKU Details
- `GET /api/v1/sku/<code>` - Полная карточка товара
  - Включает данные из `products` и `wineries`
  - Актуальная цена и остатки
  - Ссылка на изображение, сайт производителя

### Price History
- `GET /api/v1/sku/<code>/price-history` - История цен по SKU
  - Query params: `from`, `to`, `limit`, `offset`
  - Возвращает временной ряд изменений цен

### Inventory History
- `GET /api/v1/sku/<code>/inventory-history` - История остатков по SKU
  - Query params: `from`, `to`, `limit`, `offset`
  - Возвращает снимки остатков по дням
  - Используется для построения графиков

### Export
- `GET /export/search` - Экспорт результатов поиска
  - Query params: `format` (json/xlsx/pdf), фильтры как в search
- `GET /export/sku/<code>` - Экспорт карточки товара
  - Query params: `format` (json/pdf)
- `GET /export/price-history/<code>` - Экспорт истории цен
  - Query params: `format` (json/xlsx), `from`, `to`, `limit`
- `GET /export/inventory-history/<code>` - Экспорт истории остатков
  - Query params: `format` (json/xlsx), `from`, `to`, `limit`

### Static Files
- `GET /static/images/<filename>` - Статические изображения товаров
  - Формат: `<SKU>.<ext>` (jpg, jpeg, png)
  - Публичный доступ без авторизации

### AI Endpoints (Планируются - Sprint 8) 🔜

- `POST /api/v1/ai/search/semantic` - Семантический поиск по описаниям
- `POST /api/v1/ai/sommelier/chat` - Диалог с AI-сомелье
- `POST /api/v1/ai/descriptions/generate` - Генерация описаний товаров
- `GET /api/v1/ai/embeddings/status` - Статус индексации embeddings

Все AI endpoints защищены API-key авторизацией.

---

## 📤 Использование API

### Примеры запросов

#### PowerShell

```powershell
# Установка API ключа
$env:API_KEY = "ВАШ_API_КЛЮЧ"
$baseUrl = "http://localhost:18000"
$headers = @{ "X-API-Key" = $env:API_KEY }

# Поиск товаров
Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=5&in_stock=true" -Headers $headers

# Карточка SKU
$code = "D010210"
Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers

# История цен
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/price-history?from=2025-01-01&to=2025-12-31" -Headers $headers

# История остатков
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31" -Headers $headers

# Экспорт в Excel
$url = "$baseUrl/export/inventory-history/${code}?format=xlsx&limit=100"
Invoke-WebRequest $url -Headers $headers -OutFile "inventory_$code.xlsx"
```

#### curl + jq (Windows/Linux)

```bash
# Установка переменных
export API_KEY="ВАШ_API_КЛЮЧ"
export BASE_URL="http://localhost:18000"

# Поиск с фильтрами
curl -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/v1/products/search?color=red&country=Франция&limit=10" | jq

# Карточка SKU с выбором полей
curl -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/v1/sku/D010210" | \
  jq '{code, name, price_final_rub, stock_free, vivino_rating}'

# История остатков за период
curl -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/v1/sku/D010210/inventory-history?from=2025-01-01&to=2025-12-31&limit=50" | \
  jq '.items[] | {as_of, stock_total, stock_free}'
```

---

## 🔄 Синхронизация истории остатков

### Ручной запуск синхронизации

История остатков хранится в таблице `inventory_history` и используется для построения графиков и аналитики. Синхронизация выполняется скриптом:

```bash
# Из корня проекта
python scripts/sync_inventory_history.py

# Через Docker
docker compose exec api python scripts/sync_inventory_history.py

# Dry-run режим (без изменений в БД)
python scripts/sync_inventory_history.py --dry-run

# Синхронизация на определённую дату
python scripts/sync_inventory_history.py --as-of 2025-12-05T00:00:00
```

Через Makefile:

```bash
# Dry-run
make sync-inventory-history-dry-run

# Реальная синхронизация
make sync-inventory-history
```

### Автоматический запуск

#### Windows Task Scheduler

Для ежедневной синхронизации настройте задачу в Планировщике заданий:

1. Откройте **Task Scheduler** (Планировщик заданий)
2. Создайте задачу (Create Task...)
3. **Triggers**: Ежедневно в 03:00
4. **Actions**:
   - Program: `powershell.exe`
   - Arguments:
     ```
     -NoProfile -ExecutionPolicy Bypass -Command "cd 'D:\path\to\wine-assistant'; make sync-inventory-history"
     ```

#### Linux/WSL Cron

```bash
crontab -e
```

Добавьте:

```cron
0 3 * * * cd /opt/wine-assistant && make sync-inventory-history >> /var/log/wine-sync.log 2>&1
```

### Проверка данных в inventory_history

#### Через SQL

```sql
-- Последние снимки
SELECT code, stock_total, stock_free, reserved, as_of
FROM inventory_history
ORDER BY as_of DESC
LIMIT 50;

-- История по конкретному SKU
SELECT code, stock_total, stock_free, as_of
FROM inventory_history
WHERE code = 'D010210'
ORDER BY as_of DESC;
```

#### Через API

```powershell
$code = "D010210"
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2020-01-01&to=2030-12-31" | jq
```

---

## 📈 Построение графиков (Chart.js)

Проект включает веб-интерфейс `ui.html` с графиками истории цен и остатков на основе Chart.js.

### Структура графика истории

#### История цен

```javascript
async function loadPriceHistory(code) {
  const response = await apiGet(`/sku/${code}/price-history`, {
    from: '2020-01-01',
    to: '2030-12-31',
    limit: 100
  });

  const ctx = document.getElementById('priceChart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: response.items.map(p => p.effective_from),
      datasets: [{
        label: 'Цена, ₽',
        data: response.items.map(p => p.price_rub),
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.15)',
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          callbacks: {
            label: (context) => {
              const value = context.parsed.y;
              return `Цена: ${value.toLocaleString('ru-RU')} ₽`;
            }
          }
        }
      }
    }
  });
}
```

#### История остатков

```javascript
async function loadInventoryHistory(code) {
  const response = await apiGet(`/sku/${code}/inventory-history`, {
    from: '2020-01-01',
    to: '2030-12-31',
    limit: 100
  });

  const ctx = document.getElementById('inventoryChart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: response.items.map(p => p.as_of),
      datasets: [
        {
          label: 'Общий остаток',
          data: response.items.map(p => p.stock_total),
          borderColor: 'rgba(54, 162, 235, 1)',
          backgroundColor: 'rgba(54, 162, 235, 0.15)'
        },
        {
          label: 'Свободный остаток',
          data: response.items.map(p => p.stock_free),
          borderColor: 'rgba(75, 192, 192, 1)',
          backgroundColor: 'rgba(75, 192, 192, 0.15)',
          borderDash: [4, 4]
        }
      ]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true
        }
      }
    }
  });
}
```

### HTML разметка

```html
<div class="mb-3">
  <h6>История цен</h6>
  <canvas id="priceChart" height="120"></canvas>
</div>

<div class="mb-3">
  <h6>История остатков</h6>
  <canvas id="inventoryChart" height="120"></canvas>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

### Настройка визуализации

Дополнительные опции для улучшения графиков:

```javascript
// Форматирование дат на оси X
scales: {
  x: {
    ticks: {
      callback: (value) => {
        const label = this.getLabelForValue(value);
        return label ? label.slice(0, 10) : ''; // YYYY-MM-DD
      }
    }
  }
}

// Логарифмическая шкала для больших диапазонов
scales: {
  y: {
    type: 'logarithmic',
    ticks: {
      callback: (value) => Number(value).toLocaleString('ru-RU')
    }
  }
}

// Ограничение количества точек
const recentData = allData.slice(-50); // последние 50 точек
```

---

## 🧪 Тестирование

### Запуск всех тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=. --cov-report=html

# Только интеграционные
pytest tests/integration/

# Только unit-тесты
pytest tests/unit/

# Конкретный тест
pytest tests/integration/test_api_export_sku_and_price_history.py -v
```

### Smoke-check скрипты

Быстрая проверка работоспособности развернутого стенда:

```powershell
# Быстрый smoke-check (основные эндпоинты)
.\scripts\quick_smoke_check.ps1

# Полный smoke-check (все API endpoints)
.\scripts\manual_smoke_check.ps1
```

Скрипты проверяют:
- ✅ Health endpoints (`/live`, `/ready`, `/health`)
- ✅ Поиск по каталогу (`/api/v1/products/search`)
- ✅ Карточку SKU (`/api/v1/sku/<code>`)
- ✅ Историю цен (`/api/v1/sku/<code>/price-history`)
- ✅ Историю остатков (`/api/v1/sku/<code>/inventory-history`)
- ✅ Экспортные эндпоинты (JSON/XLSX/PDF)
- ✅ Проверку типов данных (number vs string)

### Структура тестов

```
tests/
├── unit/                    # Unit-тесты бизнес-логики
│   ├── test_data_quality.py
│   ├── test_date_extraction.py
│   ├── test_idempotency.py
│   ├── test_load_csv.py
│   ├── test_schemas.py
│   └── test_validation.py
├── integration/             # Интеграционные тесты API + БД
│   ├── test_api_products_search_happy.py
│   ├── test_api_export_sku_and_price_history.py
│   ├── test_price_import_etl.py
│   └── conftest.py
├── e2e/                     # End-to-end тесты (планируется)
├── conftest.py              # Общие фикстуры
└── README.md                # Описание тестовой инфраструктуры
```

### Coverage

Текущее покрытие: **>80%**

```bash
# Генерация отчёта
pytest --cov=. --cov-report=html
# Отчёт доступен в htmlcov/index.html
```

---

## 🏗️ Работа со справочником виноделен

### Импорт виноделен из PDF-каталога

Полный цикл работы с PDF-каталогом поставщика:

```bash
# 1. Извлечение сырых данных из PDF
python scripts/extract_wineries_from_pdf.py
# Результат: data/catalog/wineries_enrichment_from_pdf.xlsx

# 2. Нормализация названий поставщиков
python scripts/normalize_wineries_suppliers.py
# Результат: data/catalog/wineries_enrichment_from_pdf_norm.xlsx

# 3. Проверка соответствия с products
python scripts/check_wineries_vs_products.py
# Вывод: список поставщиков без совпадений, fuzzy-matching подсказки

# 4. Загрузка в БД (dry-run)
python -m scripts.load_wineries \
  --excel "data/catalog/wineries_enrichment_from_pdf_norm.xlsx"

# 5. Загрузка в БД (реальная)
python -m scripts.load_wineries \
  --excel "data/catalog/wineries_enrichment_from_pdf_norm.xlsx" \
  --apply
```

### Обогащение products данными из wineries

```sql
-- Обновление региона
UPDATE products p
SET region = w.region
FROM wineries w
WHERE p.supplier = w.supplier
  AND p.region IS NULL
  AND w.region IS NOT NULL;

-- Обновление сайта производителя
UPDATE products p
SET producer_site = w.producer_site
FROM wineries w
WHERE p.supplier = w.supplier
  AND p.producer_site IS NULL
  AND w.producer_site IS NOT NULL;
```

Или через скрипт:

```bash
python scripts/enrich_producers.py \
  --excel "data/catalog/wineries_enrichment_from_pdf_norm.xlsx"
```

### Использование в API

Данные из `wineries` автоматически включаются в ответы API:

```json
{
  "code": "D010210",
  "name": "Вино продукта",
  "supplier": "Lake Road - Origin Wine",
  "supplier_ru": "Лейк Роуд - Ориджин Вайн",
  "region": "Мальборо",
  "producer_site": "https://www.lakeroad.co.nz",
  "winery_name_ru": "Lake Road — Origin Wine",
  "winery_description_ru": "Полное описание винодельни..."
}
```

---

## 🔐 Работа с изображениями

### Автоматическое извлечение из Excel

При импорте прайса скрипт `load_csv.py` автоматически:
1. Извлекает изображения из Excel
2. Сохраняет в `/app/static/images/<SKU>.<ext>`
3. Заполняет `products.image_url`

```bash
python scripts/load_csv.py \
  --excel "data/inbox/Прайс.xlsx" \
  --date 2025-12-01 \
  --mapping etl/mapping_template.json \
  --skip-image-extraction=false
```

### Статическая раздача изображений

Flask автоматически раздаёт файлы из `/static/images`:

```
GET http://localhost:18000/static/images/D010210.jpg
```

URL формируется как:

```python
image_url = f"{WINE_IMAGE_BASE_URL}/{code}.{ext}"
# http://localhost:18000/static/images/D010210.jpg
```

### Использование в экспортах

#### Excel экспорт

Колонка "Фото (URL)" содержит полный URL изображения:

```
http://localhost:18000/static/images/D010210.jpg
```

#### PDF экспорт

Изображение встраивается в PDF-карточку товара:

```python
from reportlab.lib.utils import ImageReader

if image_url:
    img = ImageReader(image_path)
    pdf.drawImage(img, x, y, width, height)
```

---

## 🔧 Разработка

### Pre-commit hooks

```bash
# Установка
pre-commit install

# Ручной запуск
pre-commit run --all-files
```

Проверки:
- Ruff (линтинг)
- Black (форматирование)
- Gitleaks (поиск секретов)
- Trailing whitespace
- YAML syntax

### Makefile команды

```bash
# Установка зависимостей
make install

# Линтинг
make lint

# Форматирование
make format

# Тесты
make test

# Полная проверка (lint + test)
make check

# Coverage
make coverage

# Синхронизация остатков
make sync-inventory-history

# Сборка Docker образа
make docker-build

# Очистка кеша
make clean
```

### Обновление зависимостей

```bash
# Обновление requirements.txt
pip list --outdated
pip install -U <package>
pip freeze > requirements.txt

# Проверка уязвимостей
pip-audit

# Через Makefile
make audit
```

---

## 🎯 AI Integration (Sprint 8) - Детали реализации 🔜

> ⚠️ Этот раздел описывает планируемую реализацию. Код ещё не добавлен в репозиторий.

### Архитектура AI-слоя

```python
# api/ai/config.py
class AIConfig:
    VSELLM_API_KEY = os.getenv('VSELLM_API_KEY')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    EMBEDDING_MODEL = 'text-embedding-3-small'
    EMBEDDING_DIM = 1536

    LLM_MODELS = {
        'nano': 'gpt-4.1-nano',
        'mini': 'gpt-4o-mini',
        'pro': 'claude-sonnet-4'
    }
```

### Semantic Search

```python
# api/ai/semantic_search.py
from pgvector.psycopg2 import register_vector

async def search_wines_by_description(query: str, limit: int = 10):
    """Семантический поиск по векторным embeddings"""
    embedding = await generate_embedding(query)

    results = db.execute("""
        SELECT code, name, description_ru,
               1 - (embedding <=> %s::vector) as similarity
        FROM products
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (embedding, embedding, limit))

    return results
```

### AI Sommelier

```python
# api/ai/sommelier.py
from langgraph import StateGraph, Node

class SommelierAgent:
    def __init__(self):
        self.graph = StateGraph()
        self.memory = ConversationBufferMemory()

    async def chat(self, user_message: str, context: dict):
        """Диалог с памятью предыдущих сообщений"""
        # 1. Retrieve context from memory
        # 2. Search relevant wines
        # 3. Generate response with LLM
        # 4. Update memory
        pass
```

### Cost Optimization

```python
# api/ai/token_optimizer.py
class CascadeModelSelector:
    """Выбор модели в зависимости от сложности задачи"""

    def select_model(self, task_complexity: str) -> str:
        if task_complexity == 'simple':
            return 'gpt-4.1-nano'  # ₽0.15/1M tokens
        elif task_complexity == 'medium':
            return 'gpt-4o-mini'    # ₽1.10/1M tokens
        else:
            return 'claude-sonnet-4' # ₽23/1M tokens
```

### Примеры использования

```python
# Semantic search
POST /api/v1/ai/search/semantic
{
  "query": "легкое белое вино к рыбе",
  "limit": 10
}

# AI Sommelier chat
POST /api/v1/ai/sommelier/chat
{
  "message": "Посоветуй вино к стейку",
  "session_id": "user-123",
  "context": {
    "budget": "до 3000 руб",
    "preferences": ["сухое", "красное"]
  }
}

# Generate description
POST /api/v1/ai/descriptions/generate
{
  "code": "D010210",
  "style": "professional",
  "length": "medium"
}
```

### Мониторинг расходов

```python
# api/ai/monitoring.py
class CostTracker:
    def __init__(self):
        self.db = connect_to_db()

    def log_request(self, model: str, tokens_in: int, tokens_out: int):
        cost = calculate_cost(model, tokens_in, tokens_out)
        self.db.execute("""
            INSERT INTO ai_usage_logs
            (model, tokens_in, tokens_out, cost_rub, timestamp)
            VALUES (%s, %s, %s, %s, NOW())
        """, (model, tokens_in, tokens_out, cost))
```

### Roadmap Sprint 8

| Issue | Задача | Статус | ETA |
|-------|--------|--------|-----|
| #128 | AI Infrastructure Setup | 🔜 Открыт | Неделя 1 |
| #129 | Embeddings Generation | 🔜 Открыт | Неделя 1-2 |
| #130 | Semantic Search API | 🔜 Открыт | Неделя 2 |
| #131 | Description Generator | 🔜 Открыт | Неделя 3 |
| #132 | AI Testing Infrastructure | 🔜 Открыт | Неделя 2-4 |
| #134 | AI Sommelier (LangGraph) | 🔜 Открыт | Неделя 4-5 |
| #133 | Monitoring Dashboard | 🔜 Открыт | Неделя 5 |

### Пример расходов (1000 запросов/день) - проектная оценка

| Задача | Модель | Токены | Стоимость/день |
|--------|--------|--------|----------------|
| Embeddings генерация | text-embed-3-small | 500K | ₽1.50 |
| Базовые рекомендации | gpt-4o-mini | 1M | ₽11.00 |
| Сложные диалоги | claude-sonnet-4 | 100K | ₽23.00 |
| **ИТОГО** | | **1.6M** | **₽35.50** |

**Бюджет:** ~₽1000/месяц при активном использовании

---

## 🤝 Contribution

### Процесс разработки

1. Создайте feature branch от `master`
   ```bash
   git checkout -b feature/your-feature
   ```
2. Напишите код с тестами
3. Убедитесь в прохождении проверок:
   ```bash
   make check  # линтер + тесты
   ```
4. Создайте Pull Request с описанием изменений

### Стандарты кода
- Python 3.11+
- Type hints обязательны
- Docstrings для публичных функций
- Покрытие тестами >80%
- Ruff для линтинга
- Black для форматирования

### Коммиты
- Используйте conventional commits
- Примеры: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Ссылайтесь на Issues: `(Refs #123)`

---

## 📚 Документация

### Основная документация
- [Архитектура проекта](docs/architecture.md)
- [API спецификация](http://localhost:18000/docs)
- [Руководство по ETL](docs/etl-guide.md)

### Специализированная документация
- [Автоматический импорт изображений](README.auto_images.ru.md)
- [Справочник виноделен](README.wineries.md)
- [История остатков и графики](docs/inventory-history-guide.md)
- [Ручной smoke-check](docs/manual-smoke-check.md)
- [Экспорт через веб-интерфейс](docs/export-web-ui.md)
- [Дополнительные поля продуктов](docs/readme_block_new_products_fields_ru.md)
- [AI Integration Guide](docs/ai-integration.md) - Планируется Sprint 8

### Руководства для разработчиков
- [Windows Setup](docs/dev/dev-setup-windows.md)
- [Шпаргалка: от чистой среды до зелёных тестов](docs/dev/cheatsheet-from-clean-clone-to-green-tests.md)
- [Issue #83-84: Data Quality Gates](docs/dev/issue-83-84-notes.md)
- [Issue #85: Партиционирование](docs/dev/issue-85-partitioning-notes.md)
- [Issue #127: Винодельни и enrichment](docs/dev/issue-127-wineries-notes.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## 🔒 Безопасность

- **API Key авторизация** для защищенных endpoints
- **Валидация входных данных** через Pydantic
- **SQL injection защита** (параметризованные запросы)
- **Secrets scanning** в CI/CD (Gitleaks)
- **Security headers** в production
- **Rate limiting** для защиты от перегрузки
- **Dependency scanning** через pip-audit
- **SAST** через Semgrep
- **API Key rotation** для AI провайдеров (планируется)

---

## 📊 Производительность

- **Connection pooling** для БД
- **Партиционирование** таблиц по кварталам (Issue #85)
- **Индексы** для поиска:
  - GIN для полнотекстового поиска
  - HNSW для векторного поиска (готовность к AI)
  - B-tree для SKU и supplier
- **Эффективный экспорт** больших объемов данных
- **Pagination** по умолчанию (limit/offset)
- **Bulk operations** для массовых загрузок
- **Prepared statements** для частых запросов
- **AI Token optimization** - минимизация промптов *(планируется Sprint 8)*
- **Cascade model selection** - дешёвые модели для простых задач *(планируется Sprint 8)*
- **Redis caching** для embeddings *(планируется Sprint 9)*

---

## 📦 Технологический стек

| Категория | Технологии |
|-----------|------------|
| **Backend** | Python 3.11+, Flask, Pydantic |
| **Database** | PostgreSQL 16, pgvector, pg_trgm |
| **AI/ML** 🔜 | OpenAI API, VseLLM, LangChain, LangGraph *(planned Sprint 8)* |
| **Embeddings** 🔜 | text-embedding-3-small (1536 dim) *(planned Sprint 8)* |
| **LLM Models** 🔜 | gpt-4o-mini, claude-sonnet-4, gpt-4.1-nano *(planned Sprint 8)* |
| **Infrastructure** | Docker, Docker Compose, Gunicorn |
| **Testing** | pytest, coverage, integration tests |
| **CI/CD** | GitHub Actions, Semgrep, pip-audit |
| **Monitoring** | Structured logging, Health checks |
| **Documentation** | Swagger/OpenAPI, Markdown |
| **Code Quality** | Ruff, Black, Pre-commit hooks |
| **Export** | openpyxl, ReportLab (PDF), JSON |
| **Image Processing** | openpyxl (extraction), Flask (serving) |
| **PDF Parsing** | PyPDF2 (catalog extraction) |
| **Visualization** | Chart.js (frontend graphs) |

---

## 🎓 Learning Resources

Проект демонстрирует:
- ✅ REST API design с Flask
- ✅ ETL pipeline архитектура
- ✅ PostgreSQL с расширениями (pgvector)
- ✅ Docker containerization
- ✅ CI/CD с GitHub Actions
- ✅ Testing best practices (unit/integration/e2e)
- ✅ Data Quality Gates
- ✅ Image extraction и static file serving
- ✅ **Reference data management** (справочник виноделен)
- ✅ **Data enrichment workflows**
- ✅ **PDF parsing и нормализация данных**
- ✅ **Time-series data** (история цен и остатков)
- ✅ **Data visualization** (Chart.js graphs)
- ✅ **Automated smoke testing** (PowerShell scripts)
- 🔜 **AI/ML integration** (OpenAI API, LangChain) - *Sprint 8*
- 🔜 **Vector search** с pgvector + HNSW - *Sprint 8*
- 🔜 **LangGraph** для stateful AI conversations - *Sprint 8*
- 🔜 **Cost optimization** для LLM-приложений - *Sprint 8*

---

## 📄 Лицензия

MIT License - см. файл [LICENSE](LICENSE)

Проект можно свободно использовать как основу для собственных решений и обучения.

---

## 👥 Команда и контакты

**Maintainer:** [@glinozem](https://github.com/glinozem)

**Статус проекта:** Активная разработка

**Текущий Sprint:** Sprint 8 - AI Integration (планируется)

**Последнее обновление:** Декабрь 2025

**Полезные ссылки:**
- [GitHub Issues](https://github.com/glinozem/wine-assistant/issues)
- [Project Board](https://github.com/glinozem/wine-assistant/projects)
- VseLLM Telegram: [@vsellm_bot](https://t.me/vsellm_bot)

---

## 📝 Резюме текущего состояния проекта

Wine Assistant находится в **production-ready** состоянии после завершения Sprint 7:

### ✅ Что готово к использованию СЕЙЧАС (Sprint 1-7)
1. ✅ **Полный каталог товаров** с enrichment данными
2. ✅ **Справочник виноделен** (`wineries`) из PDF-каталога
3. ✅ **Автоматический импорт изображений** из Excel-прайсов
4. ✅ **SKU API** с историей цен и остатков
5. ✅ **История остатков** (`inventory_history`) с ежедневной синхронизацией
6. ✅ **Графики** истории цен и остатков (Chart.js)
7. ✅ **Экспорт** в XLSX/PDF/JSON с фотографиями
8. ✅ **164 автотеста** (все зелёные)
9. ✅ **Data Quality Gates** с карантином
10. ✅ **Партиционирование** таблиц
11. ✅ **Structured logging** с request tracking
12. ✅ **Smoke-check скрипты** (PowerShell)
13. ✅ **Docker-инфраструктура** готова к деплою

### 🔜 Что в АКТИВНОЙ РАЗРАБОТКЕ (Sprint 8 - AI Integration)

> **Статус:** Issues #128-134 открыты, архитектура спроектирована, реализация в очереди

1. 🔜 **AI Integration** через VseLLM/OpenAI API (Issue #128)
2. 🔜 **Semantic Search** с векторными embeddings (Issues #129, #130)
3. 🔜 **AI Description Generator** (Issue #131)
4. 🔜 **AI Sommelier** с памятью диалогов (Issue #134)
5. 🔜 **AI Testing Infrastructure** (Issue #132)
6. 🔜 **Cost Optimization** и мониторинг расходов (Issue #133)

### 🎯 Метрики готовности текущего функционала
- ✅ API стабильно и полностью документировано
- ✅ ETL pipeline обрабатывает реальные прайсы
- ✅ Все основные сценарии покрыты тестами
- ✅ Docker-окружение готово к деплою
- ✅ Справочник виноделен полностью интегрирован
- ✅ Автоимпорт изображений работает из коробки
- ✅ История остатков синхронизируется автоматически
- ✅ Графики работают в UI

### 📋 Что можно делать ПРЯМО СЕЙЧАС
- ✅ Импортировать прайсы с автоматическим извлечением фото
- ✅ Искать товары через публичный API
- ✅ Получать карточки SKU с данными виноделен
- ✅ Экспортировать каталог в Excel/PDF
- ✅ Анализировать историю цен и остатков
- ✅ Строить графики динамики (Chart.js)
- ✅ Интегрировать с фронтенд-витриной
- ✅ Настроить автоматическую синхронизацию остатков

### 🚧 Что будет ПОСЛЕ Sprint 8
- 🔜 Семантический поиск: "вино к стейку"
- 🔜 AI-рекомендации: "подбери вино к блюду"
- 🔜 Автогенерация описаний для товаров без них
- 🔜 Умный чат-сомелье с памятью диалогов

**Вывод:** Проект готов к интеграции с фронтенд-витриной **уже сейчас**. AI-функционал добавит дополнительные возможности в будущем, но не является блокером для запуска.

---

<p align="center">
  <i>Wine Assistant - от учебного проекта к production-ready AI-powered системе</i>
</p>

<p align="center">
  <strong>🍷 Made for Wine Lovers • 🏛️ Powered by Reference Data • 📈 Analytics Ready • 🤖 AI-Ready • 🚀 Built with Python</strong>
</p>
