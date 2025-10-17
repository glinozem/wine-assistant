# wine-assistant

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml)
[![Release Drafter](https://github.com/glinozem/wine-assistant/actions/workflows/release-drafter.yml/badge.svg?branch=master)](https://github.com/glinozem/wine-assistant/actions/workflows/release-drafter.yml)
[![Changelog on Release](https://github.com/glinozem/wine-assistant/actions/workflows/changelog-on-release.yml/badge.svg?branch=master)](https://github.com/glinozem/wine-assistant/actions/workflows/changelog-on-release.yml)
[![Latest release](https://img.shields.io/github/v/release/glinozem/wine-assistant?sort=semver)](https://github.com/glinozem/wine-assistant/releases)

Мини-API и база для ассистента по вину: поиск и карточки товаров, **две цены** (прайс/финальная), **история цен**, **история остатков**, индексы для быстрых выборок и готовые миграции.

---

## ✨ Что уже есть

- **Две цены в `products`**
  `price_list_rub`, `price_final_rub` (+ бэкофил из старого `price_rub`). Индексы по обеим.
- **История цен** — `product_prices` + `upsert_price(..)`
  - защита от перекрытия интервалов: `EXCLUDE USING gist` с `btree_gist`
  - чек неотрицательной цены
  - уникальный ключ `(code, effective_from)`
- **История остатков** — `inventory_history` + `upsert_inventory(..)`
  индекс `(code, as_of DESC)` для таймсерийных запросов.
- **Поиск**
  GIN по `products.search_text` на `pg_trgm`; `vector` включён «на будущее».
- **API (key-auth через `X-API-Key`)**
  - `GET /sku/{code}/price-history?limit=&offset=`
  - `GET /sku/{code}/inventory-history?from=&to=&limit=&offset=`
- **Swagger/OpenAPI** — UI рядом с сервисом (`/docs` и `/openapi.json`).
- **Миграции** — идемпотентные SQL + скрипт `scripts/migrate.ps1`.
- **CI/CD**
  - Release Drafter — черновик релиза из PR.
  - **Changelog on Release** — генерация `CHANGELOG.md` и **авто-PR** через PAT
    (`CHANGELOG_PR_PAT`, права: Contents RW, Pull Requests RW, Commit Statuses RW; ограничен на этот репозиторий).

---

## 🚀 Быстрый старт

### Требования
Docker + Docker Compose, PowerShell (Windows). Для локального API — Python (см. `api/`).

### Поднять инфраструктуру и применить миграции
```powershell
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant
docker compose up -d

# применить все .sql из db/migrations
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
Переменные окружения (пример)
Создайте .env при необходимости:

dotenv
Копировать код
API_PORT=18000
API_KEY=mytestkey
DATABASE_URL=postgresql://postgres:postgres@db:5432/wine_db
Проверка API
bash
Копировать код
# история цен
curl -H "X-API-Key: mytestkey" "http://127.0.0.1:18000/sku/D009704/price-history?limit=5"

# история остатков
curl -H "X-API-Key: mytestkey" "http://127.0.0.1:18000/sku/D009704/inventory-history?from=2025-01-01&to=2025-12-31&limit=5"
Swagger / OpenAPI
UI: http://127.0.0.1:18000/docs

Спецификация: http://127.0.0.1:18000/openapi.json

Если пути отличаются — проверьте конфиг в api/app.py.

🗄️ Схема БД (PostgreSQL)
Расширения: pg_trgm, vector, btree_gist.

products
price_list_rub numeric, price_final_rub numeric (+ индексы).

product_prices

code text (FK → products(code)), price_rub numeric, effective_from ts, effective_to ts

индексы: idx_product_prices_open, ux_product_prices_code_from

ограничения: product_prices_no_overlap, chk_product_prices_nonneg

функции: upsert_price(text, numeric, timestamp/timestamptz)

inventory_history
code, stock_total, reserved, stock_free, as_of ts
индекс: idx_inventory_history_code_time
функции: upsert_inventory(text, numeric, numeric, numeric, timestamp/timestamptz)

Служебные SQL:

db/migrations/2025-10-14-price-history-guardrails.sql — ограничения и индексы.

db/migrations/2025-10-14-price-check.sql — чек неотрицательных цен.

db/migrations/2025-10-14-diagnostics.sql — проверка индексов/перекрытий/несоответствий.

🔐 Аутентификация
Все эндпоинты ожидают заголовок:

makefile
Копировать код
X-API-Key: <ваш_ключ>
Ключ задаётся в настройках сервиса/окружении (см. .env и api/app.py).

🤖 CI/CD и релизы
Release Drafter создаёт черновик релиза из PR’ов.

Changelog on Release:

триггеры: release: [published, edited] + ручной workflow_dispatch

генерирует CHANGELOG.md и открывает авто-PR из ветки docs/changelog/vX.Y.Z

использует секрет CHANGELOG_PR_PAT (fine-grained PAT, ограниченный на этот репозиторий).

Чтобы PR с changelog проходили без подвисших проверок:

создайте PAT со Scope: Contents: RW, Pull Requests: RW, Commit Statuses: RW;

добавьте секрет репозитория CHANGELOG_PR_PAT;

workflow уже настроен на использование PAT и least-privilege (persist-credentials: false).

🧑‍💻 Разработка
Любые изменения схемы — отдельный .sql в db/migrations/ + scripts/migrate.ps1.

Windows/UTF-8: используйте chcp 65001 и Get-Content -Raw | psql -f -, чтобы избежать проблем кодировки.

Линтеры/проверки — см. workflow CI. В репозитории настроен pre-commit.

📝 Changelog
Файл CHANGELOG.md генерируется автоматически и приезжает авто-PR’ом.
Список релизов — во вкладке Releases.

🧭 Roadmap (коротко)
API: пагинация по умолчанию, сортировки, POST-обёртки над upsert_* с валидацией.

БД: переход на timestamptz/numeric(12,2), партиционирование inventory_history.

Поиск: улучшить FTS, подключить эмбеддинги (vector) и гибридный поиск.

Наблюдаемость: health/ready, метрики Prometheus, структурные логи.

Безопасность: JWT/rotation для ключей, rate-limit.

DX: Makefile/Taskfile, dev-compose с авто-перезапуском, сборка образа в GHCR.

📄 Лицензия
TBD.
