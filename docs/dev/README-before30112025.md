# Wine Assistant 🍷

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Semgrep](https://github.com/glinozem/wine-assistant/actions/workflows/semgrep.yml/badge.svg)](../../actions/workflows/semgrep.yml)
[![Secrets](https://github.com/glinozem/wine-assistant/actions/workflows/secrets.yml/badge.svg)](../../actions/workflows/secrets.yml)

**Production-ready система управления винным каталогом** с REST API, ETL-пайплайном, AI-сомелье и расширенными возможностями экспорта данных.

Изначально учебный проект, Wine Assistant вырос в полноценное решение, демонстрирующее best practices современной backend-разработки на Python с интеграцией AI/ML.

**Текущий статус:** Активная разработка • 164+ тестов • Production-ready архитектура • AI Integration (Sprint 8)

---

## 🎯 Ключевые возможности

### API & Интеграции
- **REST API** с полной Swagger документацией
- **Защищенные endpoints** с API-key авторизацией
- **Structured JSON logging** с request tracking
- **Health checks** (liveness/readiness) для Kubernetes
- **Rate limiting** для защиты от перегрузки
- **Версионирование API** через URL префиксы (`/api/v1/`)

### 🤖 AI Capabilities (NEW)
- **OpenAI/VseLLM интеграция** для LLM-функций (Issue #128)
- **Векторные embeddings** для семантического поиска (Issue #129)
- **Semantic Search** по описаниям вин (Issue #130)
- **AI Wine Description Generator** - автогенерация описаний (Issue #131)
- **AI Wine Sommelier** с памятью разговора (LangGraph) (Issue #134)
- **AI Monitoring Dashboard** для отслеживания расходов (Issue #133)
- **Cascade Model Architecture** (nano → mini → sonnet-4) для оптимизации затрат

### Управление данными
- **ETL Pipeline** для импорта прайс-листов (Excel/CSV)
- **Автоматический импорт изображений** из Excel → static/images
- **История цен** с автоматическим версионированием
- **Карантин данных** для невалидных записей (Data Quality Gates)
- **Идемпотентность** загрузок через SHA-256 хеши
- **Партиционирование** таблиц по кварталам для масштабирования

### Экспорт и отчеты
- **Множественные форматы:** JSON, Excel (.xlsx), PDF
- **Unicode поддержка** в PDF (кириллица, символ ₽)
- **Фиксированный набор полей** для каждого типа экспорта
- **Эффективный экспорт** больших объемов данных
- **Экспорт со ссылками на фотографии** товаров

### Инфраструктура
- **Docker Compose** окружение с PostgreSQL 16 + pgvector
- **Автоматические миграции** БД с версионированием
- **Статическая раздача изображений** через `/static/images`
- **CI/CD Pipeline** с GitHub Actions
- **Pre-commit hooks** для проверки кода

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
│         AI/ML Layer (NEW - Sprint 8)         │
│  • OpenAI/VseLLM Integration                 │
│  • Embeddings Generator (text-embed-3-small) │
│  • Semantic Search Engine                    │
│  • AI Sommelier (LangGraph)                  │
│  • Token Optimizer & Cost Tracking           │
├──────────────────────────────────────────────┤
│         Business Logic                       │
│  • Product Service                           │
│  • Price Management                          │
│  • Export Service (XLSX/PDF/JSON)            │
│  • Data Validation (Pydantic)                │
│  • Image Extraction & Storage                │
├──────────────────────────────────────────────┤
│         Data Access Layer                    │
│  • PostgreSQL 16 + pgvector                  │
│  • Migrations (Alembic-style)                │
│  • Connection Pooling                        │
│  • Partitioned Tables (quarterly)            │
│  • Vector Similarity Search (HNSW)           │
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

#### 2. AI Layer (`/api/ai`) - NEW 🆕
- `config.py` - Конфигурация AI провайдеров (OpenAI/VseLLM)
- `llm_service.py` - Унифицированный сервис для LLM
- `embeddings.py` - Генерация и управление embeddings
- `semantic_search.py` - Векторный поиск по описаниям
- `sommelier.py` - AI-сомелье с памятью разговора
- `token_optimizer.py` - Оптимизация промптов и расходов
- `model_selector.py` - Каскадный выбор моделей

#### 3. ETL Layer (`/scripts`, `/etl`)
- `load_csv.py` - Основной ETL pipeline
- `load_utils.py` - Утилиты работы с БД
- `date_extraction.py` - Интеллектуальное извлечение дат
- `idempotency.py` - Проверка дубликатов через хеши
- `data_quality.py` - Data Quality Gates
- `image_extractor.py` - Извлечение изображений из Excel

#### 4. Database Layer (`/db`)
- Миграции с версионированием
- Партиционирование по кварталам
- Хранимые процедуры для upsert
- Карантинная таблица для DQ
- Векторные индексы (HNSW) для pgvector

---

## 🔌 API Endpoints

### Публичные endpoints

```http
GET /live                          # Liveness probe
GET /ready                         # Readiness probe
GET /api/v1/products               # Список товаров с пагинацией
GET /api/v1/products/search        # Поиск по параметрам
GET /static/images/<filename>      # Раздача изображений товаров
```

### Защищенные endpoints (требуют X-API-Key)

```http
GET /api/v1/sku/{code}                          # Карточка товара
GET /api/v1/sku/{code}/price-history            # История цен
GET /api/v1/sku/{code}/inventory-history        # История остатков

# Экспорт данных
GET /api/v1/export/search?format=json|xlsx|pdf                 # Экспорт результатов поиска
GET /api/v1/export/sku/{code}?format=json|pdf                  # Карточка товара
GET /api/v1/export/price-history/{code}?format=json|xlsx       # История цен по SKU
```

### 🤖 AI Endpoints (Sprint 8) - Coming Soon

```http
POST /api/v1/ai/recommend           # Умные рекомендации от AI-сомелье
POST /api/v1/ai/search/semantic     # Семантический поиск по описанию
POST /api/v1/ai/describe/{code}     # Генерация описания вина
GET  /api/v1/ai/health              # Health check AI-сервисов
GET  /api/v1/ai/metrics             # Метрики использования AI (токены, расходы)
```

### Примеры использования

```bash
# Получение API ключа из .env
API_KEY=$(grep API_KEY .env | cut -d '=' -f2)

# Поиск товаров (публичный endpoint)
curl "http://localhost:18000/api/v1/products/search?q=Brunello&in_stock=true"

# Карточка товара (требует API key)
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:18000/api/v1/sku/D009704"

# Экспорт в Excel
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:18000/api/v1/export/search?format=xlsx&limit=100" \
  -o wine_catalog.xlsx

# AI рекомендации (Sprint 8)
curl -X POST -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preferences": "люблю сухие красные вина из Италии"}' \
  "http://localhost:18000/api/v1/ai/recommend"
```

---

## 📥 Загрузка данных (ETL)

### Импорт прайс-листа из Excel с автоматическим извлечением изображений

```bash
# Активация виртуального окружения
source .venv/bin/activate  # Linux/macOS

# Настройка подключения к БД
export DB_HOST=localhost
export DB_PORT=15432
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_NAME=wine_db

# Настройка путей для изображений
export WINE_IMAGE_DIR=./static/images
export WINE_IMAGE_BASE_URL=http://localhost:18000/static/images

# Загрузка прайс-листа с автоматическим извлечением фото
python -m scripts.load_csv --excel "data/price_list.xlsx"

# Или через Makefile
make load-price EXCEL_PATH="./data/price_list.xlsx"
```

### Автоматический импорт изображений

ETL pipeline автоматически:
1. Извлекает встроенные изображения из Excel (`openpyxl`)
2. Сопоставляет изображение со SKU по строке
3. Сохраняет в `/app/static/images/<SKU>.<ext>`
4. Формирует публичный URL: `http://localhost:18000/static/images/<SKU>.<ext>`
5. Заполняет поле `products.image_url` в БД

Изображения доступны через:
```bash
# Прямой доступ к изображению
curl http://localhost:18000/static/images/D009704.jpg -o wine.jpg

# В API ответах поле image_url содержит полный URL
curl http://localhost:18000/api/v1/sku/D009704 | jq '.image_url'
```

### Поддерживаемые форматы
- Excel (.xlsx, .xls) с встроенными изображениями
- CSV с разделителями (`,`, `;`, `\t`)
- Автоопределение колонок и форматов
- Извлечение даты из имени файла или ячейки Excel

### Data Quality проверки
- Валидация обязательных полей
- Проверка диапазонов цен и скидок
- Контроль дубликатов через SHA-256
- Карантин для невалидных записей (Issue #84)

---

## 🤖 AI Integration Guide (Sprint 8)

### Подготовка

```bash
# 1. Получить API ключ VseLLM
# Telegram: @vsellm_bot
# Оплата в рублях, без VPN

# 2. Добавить в .env
echo "VSELLM_API_KEY=your-api-key-here" >> .env
echo "VSELLM_BASE_URL=https://api.vsellm.ru/v1" >> .env
echo "AI_ENABLED=true" >> .env

# 3. Установить зависимости AI
pip install openai langchain langgraph
```

### Генерация embeddings для каталога

```bash
# Batch-генерация embeddings для всех товаров
python -m scripts.generate_embeddings --batch-size 100

# Прогресс и cost tracking
# Processing: 1523/1523 wines
# Tokens used: 145,230
# Cost: ₽0.44 (at 3₽/1M tokens)
```

### Использование AI Sommelier

```python
from api.ai.sommelier import WineSommelier

# Инициализация с памятью разговора
sommelier = WineSommelier(session_id="user_123")

# Запрос рекомендации
response = sommelier.recommend(
    user_input="Хочу что-то к стейку из говядины, бюджет до 3000₽"
)

print(response.recommendations)  # Список SKU с пояснениями
print(response.reasoning)        # Объяснение выбора
print(response.cost_rubles)      # Стоимость запроса в рублях
```

### Мониторинг расходов AI

```bash
# Просмотр метрик через API
curl -H "X-API-Key: $API_KEY" \
  http://localhost:18000/api/v1/ai/metrics

# Ответ:
{
  "total_tokens_today": 45230,
  "cost_today_rub": 1.35,
  "requests_today": 127,
  "avg_latency_ms": 850,
  "model_usage": {
    "gpt-4o-mini": 89,
    "claude-sonnet-4": 12
  }
}
```

---

## 🧪 Тестирование

### Запуск всех тестов

```bash
# Полный прогон (unit + integration)
pytest -q -rs

# Только unit-тесты
pytest tests/unit -q

# Только AI-тесты (Sprint 8)
pytest tests/unit/ai -q
pytest tests/integration/ai -q

# С покрытием
pytest --cov=api --cov=scripts --cov-report=html
```

### Метрики тестирования
- **164+ тестов** всех уровней
- **Unit тесты:** валидация, схемы, утилиты, AI-компоненты
- **Integration тесты:** API + БД взаимодействие, AI endpoints
- **E2E тесты:** полный цикл загрузки и экспорта
- **Coverage:** >80% для критического кода

---

## 🏗️ Development Setup

### Использование Makefile

```bash
# Основные команды
make dev-up          # Поднять окружение
make dev-down        # Остановить контейнеры
make db-reset        # Пересоздать БД с нуля
make test-unit       # Unit-тесты
make test-int        # Интеграционные тесты
make test-ai         # AI-тесты (Sprint 8)
make check           # Линтер + все тесты

# Работа с данными
make load-price EXCEL_PATH="./data/price.xlsx"  # Загрузить прайс
make show-quarantine                              # Просмотр карантина
make generate-embeddings                          # Генерация AI embeddings

# Дополнительные команды
make lint            # Запуск линтера (ruff)
make format          # Форматирование кода
make clean           # Очистка временных файлов
```

### Pre-commit hooks

```bash
# Установка хуков
pre-commit install

# Ручной запуск
pre-commit run --all-files

# Обновление хуков
pre-commit autoupdate
```

---

## 📈 Мониторинг и метрики

### Health Checks

```bash
# Liveness - приложение живо
curl http://localhost:18000/live

# Readiness - готово принимать запросы
curl http://localhost:18000/ready

# AI Health - статус AI сервисов (Sprint 8)
curl http://localhost:18000/api/v1/ai/health
```

### Structured Logging

Все логи в JSON формате с контекстом:

```json
{
  "timestamp": "2025-11-27T10:30:45.123Z",
  "level": "INFO",
  "request_id": "req_20251127_103045_a1b2c3d4",
  "method": "GET",
  "path": "/api/v1/products/search",
  "duration_ms": 45.3,
  "status_code": 200,
  "ai_tokens_used": 1250,
  "ai_cost_rub": 0.015
}
```

---

## 🗺️ Roadmap

### ✅ Реализовано (Sprint 1-7)
- [x] REST API с Swagger документацией
- [x] ETL pipeline для прайс-листов
- [x] Система версионирования цен
- [x] Карантин для невалидных данных (Issue #84)
- [x] Data Quality Gates (Issue #83)
- [x] Экспорт в Excel/PDF/JSON (Issue #69)
- [x] Автоматический импорт изображений из Excel
- [x] Structured JSON logging
- [x] Request tracking с уникальными ID
- [x] Партиционирование таблиц (Issue #85)
- [x] Rate limiting для ключевых эндпоинтов
- [x] Идемпотентные миграции БД
- [x] Unit тесты для ETL (Issue #91)

### 🚧 В разработке (Sprint 8)
- [ ] **Issue #128**: OpenAI API Integration - базовая интеграция VseLLM
- [ ] **Issue #129**: Wine Embeddings Infrastructure - генерация векторов
- [ ] **Issue #130**: Semantic Search Endpoint - семантический поиск
- [ ] **Issue #131**: AI Wine Description Generator - автогенерация описаний
- [ ] **Issue #132**: AI Testing Infrastructure - тесты для AI-компонентов
- [ ] **Issue #134**: AI Wine Sommelier with Memory - умный сомелье (LangGraph)

### 📋 Планируется (Sprint 9+)
- [ ] **Issue #133**: AI Monitoring Dashboard - дашборд расходов AI
- [ ] **Issue #127**: Integrate DW 2025 catalog - новый каталог поставщика
- [ ] **Issue #67**: Telegram-бот для поиска вин
- [ ] **Issue #68**: Векторный поиск с pgvector (расширенный)
- [ ] **Issue #66**: Примеры клиентов (Python, JavaScript)
- [ ] **Issue #63**: Prometheus метрики
- [ ] **Issue #64**: Sentry для Error Tracking
- [ ] **Issue #61**: Performance тесты (Load Testing)
- [ ] **Issue #60**: E2E тесты критических сценариев
- [ ] **Issue #59**: Integration тесты API endpoints

Подробный roadmap: [`docs/ROADMAP_v3_RU.md`](docs/ROADMAP_v3_RU.md)

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

- [Архитектура проекта](docs/architecture.md)
- [API спецификация](http://localhost:18000/docs)
- [Руководство по ETL](docs/etl-guide.md)
- [Автоматический импорт изображений](README.auto_images.ru.md)
- [AI Integration Guide](docs/ai-integration.md) - NEW 🆕
- [Windows Setup](docs/dev/dev-setup-windows.md)
- [Шпаргалка: от чистой среды до зелёных тестов](docs/dev/cheatsheet-from-clean-clone-to-green-tests.md)
- [Issue #83-84: Data Quality Gates](docs/dev/issue-83-84-notes.md)
- [Issue #85: Партиционирование](docs/dev/issue-85-partitioning-notes.md)
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
- **API Key rotation** для AI провайдеров

---

## 📊 Производительность

- **Connection pooling** для БД
- **Партиционирование** таблиц по кварталам (Issue #85)
- **Индексы** для поиска (GIN для полнотекстового, HNSW для векторного)
- **Эффективный экспорт** больших объемов данных
- **Pagination** по умолчанию (limit/offset)
- **Bulk operations** для массовых загрузок
- **Prepared statements** для частых запросов
- **AI Token optimization** - минимизация промптов
- **Cascade model selection** - дешёвые модели для простых задач
- **Redis caching** для embeddings (планируется)

---

## 📦 Технологический стек

| Категория | Технологии |
|-----------|------------|
| **Backend** | Python 3.11+, Flask, Pydantic |
| **Database** | PostgreSQL 16, pgvector, pg_trgm |
| **AI/ML** 🆕 | OpenAI API, VseLLM, LangChain, LangGraph |
| **Embeddings** 🆕 | text-embedding-3-small (1536 dim) |
| **LLM Models** 🆕 | gpt-4o-mini, claude-sonnet-4, gpt-4.1-nano |
| **Infrastructure** | Docker, Docker Compose, Gunicorn |
| **Testing** | pytest, coverage, integration tests |
| **CI/CD** | GitHub Actions, Semgrep, pip-audit |
| **Monitoring** | Structured logging, Health checks, AI metrics |
| **Documentation** | Swagger/OpenAPI, Markdown |
| **Code Quality** | Ruff, Black, Pre-commit hooks |
| **Export** | openpyxl, ReportLab (PDF), JSON |
| **Image Processing** | openpyxl (extraction), Flask (serving) |

---

## 💰 AI Cost Optimization

### Стратегия оптимизации расходов

1. **Cascade Model Architecture**
   - Simple tasks → `gpt-4.1-nano` (8₽/млн токенов input)
   - Standard tasks → `gpt-4o-mini` (11₽/млн токенов)
   - Complex reasoning → `claude-sonnet-4` (230₽/млн токенов)

2. **Token Optimization**
   - Минимизация промптов (убрать "пожалуйста", "спасибо")
   - Резюмирование длинных контекстов
   - Кэширование частых embeddings в Redis

3. **Batch Processing**
   - Генерация embeddings батчами (100 SKU за раз)
   - Асинхронная обработка через Celery (планируется)

4. **VseLLM vs OpenAI Direct**
   - Экономия 20-25% vs прямое подключение
   - Оплата в рублях, НДС, без VPN
   - Полная совместимость с OpenAI API

### Пример расходов (1000 запросов/день)

| Задача | Модель | Токены | Стоимость/день |
|--------|--------|--------|----------------|
| Embeddings генерация | text-embed-3-small | 500K | ₽1.50 |
| Базовые рекомендации | gpt-4o-mini | 1M | ₽11.00 |
| Сложные диалоги | claude-sonnet-4 | 100K | ₽23.00 |
| **ИТОГО** | | **1.6M** | **₽35.50** |

**Бюджет:** ~₽1000/месяц при активном использовании

---

## 📄 Лицензия

MIT License - см. файл [LICENSE](LICENSE)

Проект можно свободно использовать как основу для собственных решений и обучения.

---

## 👥 Команда и контакты

**Maintainer:** [@glinozem](https://github.com/glinozem)

**Статус проекта:** Активная разработка (Sprint 8 - AI Integration)

**Последнее обновление:** Ноябрь 2025

**Полезные ссылки:**
- [GitHub Issues](https://github.com/glinozem/wine-assistant/issues)
- [Project Board](https://github.com/glinozem/wine-assistant/projects)
- VseLLM Telegram: [@vsellm_bot](https://t.me/vsellm_bot)

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
- 🆕 **AI/ML integration** (OpenAI API, LangChain)
- 🆕 **Vector search** с pgvector + HNSW
- 🆕 **LangGraph** для stateful AI conversations
- 🆕 **Cost optimization** для LLM-приложений

---

<p align="center">
  <i>Wine Assistant - от учебного проекта к production-ready AI-powered системе</i>
</p>

<p align="center">
  <strong>🤖 Powered by AI • 🍷 Made for Wine Lovers • 🚀 Built with Python</strong>
</p>
