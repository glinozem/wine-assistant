# 🍷 Wine Assistant

[![CI](https://github.com/glinozem/wine-assistant/workflows/CI/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Tests](https://github.com/glinozem/wine-assistant/workflows/Tests/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Release Drafter](https://github.com/glinozem/wine-assistant/workflows/Release%20Drafter/badge.svg)](https://github.com/glinozem/wine-assistant/actions)
[![Coverage](https://img.shields.io/badge/coverage-60.64%25-green.svg)](https://github.com/glinozem/wine-assistant)
[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/glinozem/wine-assistant/releases)
[![Python](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Современная система каталога и управления ценами на вино**
>
> Production‑ready Flask API + PostgreSQL (pg_trgm, *опционально* pgvector) с историзацией цен, автоматизированным ETL, идемпотентным импортом и структурированным JSON‑логированием.

**Текущая версия:** 0.3.0
**Последнее обновление:** 7 ноября 2025

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Что нового](#-что-нового)
- [Архитектура](#-архитектура)
- [Быстрый старт](#-быстрый-старт)
- [Документация API](#-документация-api)
- [Автоматизированный ETL](#-автоматизированный-etl)
- [Конфигурация](#-конфигурация)
- [Разработка](#-разработка)
- [Тестирование](#-тестирование)
- [Mini: как поднимается БД в CI](#-mini-как-поднимается-бд-в-ci-github-actions)
- [Развертывание](#-развертывание)
- [Мониторинг и наблюдаемость](#-мониторинг-и-наблюдаемость)
- [Устранение неполадок](#-устранение-неполадок)
- [Дорожная карта](#-дорожная-карта)
- [Участие в разработке](#-участие-в-разработке)
- [Лицензия](#-лицензия)

---

## 🚀 Возможности

### Основной функционал
- 📦 **Каталог вин** — товары, финальные цены, остатки и история.
- 📈 **Историзация цен** — `product_prices` с временными интервалами.
- 🔍 **Поиск** — полнотекстовый поиск с `pg_trgm` + фильтры.
- 💰 **Двойная система цен** — прайс‑лист (`price_list_rub`) и финальная (`price_final_rub`); гибкая логика скидок (по файлу и/или по фикс. ячейке).
- 📊 **История** — аудит изменений цен и остатков.
- 📥 **ETL‑конвейер** — импорт Excel/CSV с автоопределением кодировки и дат, идемпотентность загрузок.

### Для production
- 🛡️ **API‑ключ** для защищённых методов, CORS.
- 🧯 **Rate limiting** (Flask‑Limiter).
- 🏥 **Health‑эндпойнты** — `/live`, `/ready`, `/version` (+ проверка индексов/ограничений).
- 🐳 **Docker Compose** — healthchecks и зависимость сервисов.
- 🧪 **Тесты** — `pytest`, покрытие на CI: **60.64%**.

---

## 🆕 Что нового

### Release notes (добавлено в релизные заметки)
- **CI:** PostgreSQL 14 на `localhost:15432` + readiness‑проба.
- **CI:** автозагрузка схем (idempotency + products/inventory/price history).
- **Тесты:** стабилизация `upsert_records()` в CI (фикс порядка инициализации БД и подключения).
- _Фоллоуапы — отдельными PR._

### Mini README‑секция: “How CI DB is provisioned” — см. ниже отдельный раздел.

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Wine Assistant                           │
├─────────────────────────────────────────────────────────────────┤
│  ETL (Excel/CSV, SHA256, Scheduler)  →  Flask API  → PostgreSQL  │
│  • Auto-date • Archive • Logs         • Swagger • Limits • Auth  │
│  • Idempotency • Validation           • Health • JSON‑logging    │
└─────────────────────────────────────────────────────────────────┘
```

### Технологический стек

| Компонент | Технология | Назначение |
|---|---|---|
| Backend | Flask 3.x | REST API |
| БД (локально) | PostgreSQL 16 (`pgvector/pgvector:pg16`) | Хранилище, опционально векторные индексы |
| БД (CI) | PostgreSQL 14 | Быстрый старт на GitHub Actions |
| Поиск | `pg_trgm` | ILIKE/похожесть по строкам |
| Документация | Flasgger / OpenAPI | Swagger UI `/docs` |
| ETL | pandas, openpyxl | Загрузка/нормализация данных |
| Контейнеры | Docker Compose | Локальная среда |
| Логи | python‑json‑logger | Структурированные логи |
| Лимиты | Flask‑Limiter | Защита от перегрузок |

> В локальном Docker установлена TZ=`Europe/Moscow` для API и БД.

---

## ⚡ Быстрый старт

```bash
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# Запуск PostgreSQL + API + Adminer
docker compose up -d

# Проверка статуса контейнеров
docker compose ps
```

**Порты по умолчанию**
- 🗄 PostgreSQL: `localhost:15432`
- 🌐 API: `http://localhost:18000`
- 🛠 Adminer: `http://localhost:18080`

**Проверка health‑эндпойнтов**
```bash
# Linux/macOS
curl -s http://127.0.0.1:18000/ready   | python -m json.tool
curl -s http://127.0.0.1:18000/live    | python -m json.tool
curl -s http://127.0.0.1:18000/version | python -m json.tool

# Windows (PowerShell)
Invoke-RestMethod http://127.0.0.1:18000/ready   | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:18000/live    | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:18000/version | ConvertTo-Json -Depth 10
```

**Минимальный `.env`**
```env
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db

API_KEY=your-secret-api-key-minimum-32-chars
FLASK_HOST=0.0.0.0
FLASK_PORT=8000
FLASK_DEBUG=0
APP_VERSION=0.3.0

CORS_ORIGINS=*
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=1
RATE_LIMIT_PUBLIC=100/hour
RATE_LIMIT_PROTECTED=1000/hour
```

---

## 📚 Документация API

- **Swagger UI:** `http://localhost:18000/docs`
  _(если включен Flasgger; эндпойнты снабжены docstring‑ами для генерации схемы)_
- **Health:**
  - `GET /live` — проверка, что процесс жив.
  - `GET /ready` — готовность + проверки соединения с БД и индексов.
  - `GET /version` — текущая версия приложения.
- **Каталог/поиск (примеры):**
  - `GET /search?q=...`
  - `GET /sku/<code>`
  - `GET /sku/<code>/price_history`

**Аутентификация**
Для защищённых методов используйте заголовок `X-API-Key` со значением из `.env` (`API_KEY`).

---

## 🤖 Автоматизированный ETL

- **Идемпотентность** — контроль дублей через SHA256 и таблицу `dw_files`.
- **Автоизвлечение даты** — из имени файла и/или Excel‑шапки (ячейки A2..B8).
- **Скидки** — по колонке файла и/или по фиксированной ячейке (например, `S5`).
- **Архивирование** — успешные файлы → `data/archive/YYYY-MM-DD/`.
- **Логи** — JSON‑логи в `logs/import.log`.

Примеры запуска:
```bash
# Excel: автоопределение даты
python scripts/load_csv.py --excel "data/inbox/Price_2025_01_20.xlsx"

# Excel: явная дата + скидка из ячейки
python scripts/load_csv.py --excel "Price.xlsx" --asof 2025-01-20 --discount-cell S5

# CSV
python scripts/load_csv.py --csv "products.csv" --asof 2025-01-20
```

---

## ⚙️ Конфигурация

См. `.env.example` и пример `.env` выше.
В `docker-compose.yml`:
- **TZ** установлен в `Europe/Moscow` для согласованности времени.
- Сервис `api` зависит от `db` (healthcheck).

---

## 🛠 Разработка

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
pre-commit install

# Локальная БД
docker compose up -d db

# Применить схемы (локально, если нужно)
psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" -f tests/fixtures/schema.sql
psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" -f tests/fixtures/schema_prices.sql

# Запуск API
python -m api.app
```

---

## 🧪 Тестирование

```bash
# Все тесты
pytest

# Покрытие
pytest --cov=api --cov=scripts --cov=etl --cov-report=term --cov-report=html
# HTML-отчёт: htmlcov/index.html
```

> На CI текущее покрытие: **60.64%**.

---

## 🧩 Mini: как поднимается БД в CI (GitHub Actions)

**1) Поднимаем PostgreSQL 14 с readiness‑пробой**
```yaml
services:
  postgres:
    image: postgres:14
    env:
      POSTGRES_DB: wine_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: dev_local_pw
    ports:
      - 15432:5432
    options: >-
      --health-cmd="pg_isready -U postgres -d wine_db"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=10
```

**2) Ждём готовности**
```bash
for i in {1..30}; do
  pg_isready -h localhost -p 15432 -U postgres -d wine_db && break
  sleep 2
done
```

**3) Автозагрузка схем и расширений**
```bash
psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" \
  -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" \
  -f tests/fixtures/schema.sql

psql "postgresql://postgres:dev_local_pw@localhost:15432/wine_db" \
  -f tests/fixtures/schema_prices.sql
```

**4) Экспорт переменных окружения**
```bash
export PGHOST=localhost
export PGPORT=15432
export PGUSER=postgres
export PGPASSWORD=dev_local_pw
export PGDATABASE=wine_db
```

**5) Запуск pytest с покрытием**
```bash
pytest -v --cov=api --cov=scripts --cov=etl --cov-report=xml --cov-report=term
```

> ✅ Благодаря автозагрузке схем тест `test_upsert_records_insert_and_update` стабилен; БД готова до старта тестов.

---

## 🚀 Развертывание

**Checklist (сжатый):** HTTPS, секретный `API_KEY`, корректные CORS, бэкапы БД, алерты, лимиты запросов, мониторинг `/ready`, ротация логов, ресурсы контейнеров.

**Пример reverse proxy (nginx):**
```nginx
location / {
  proxy_pass http://localhost:18000;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 📊 Мониторинг и наблюдаемость

- **JSON‑логи** — удобно для ELK/Loki/Datadog.
- **Health‑пробы** — периодическая проверка `/ready` + метрики задержки коннекта к БД.
- **DB‑метрики** — активные соединения, размер БД, медленные запросы.

---

## 🔧 Устранение неполадок

- **401 Unauthorized** — проверьте заголовок `X-API-Key` и значение `API_KEY`.
- **429 Too Many Requests** — превышены лимиты (`X-RateLimit-*`).
- **503 на /ready** — проверьте, что БД запущена и применены схемы/индексы.
- **Windows PowerShell** — если нет `jq`, используйте `Invoke-RestMethod | ConvertTo-Json -Depth 10`.
- **ETL** — смотрите `logs/import.log`, проверьте кодировку файла и корректность колонок.

---

## 🗺️ Дорожная карта

- Спринт 4b — интеграционные/E2E тесты, улучшение поиска.
- Спринт 5 — расширенный поиск (векторный), Telegram‑бот, экспорт.
- Спринт 6+ — интеграции (Email/Telegram), аналитика, multi‑tenant.

---

## 🤝 Участие в разработке

- Conventional Commits, pre‑commit hooks.
- Pull Request шаблоны и Release Drafter — релизные заметки формируются автоматически.
- Тесты обязательны; линтеры (`ruff`) и форматирование кода — обязательны.

---

## 📄 Лицензия

Проект распространяется по лицензии MIT — см. файл [LICENSE](LICENSE).

---

<div align="center">

**Сделано с ❤️ для винной индустрии 🍷**

</div>
