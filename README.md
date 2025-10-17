# Wine Assistant — API & ETL

[![CI](https://github.com/glinozem/wine-assistant/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Release Drafter](https://github.com/glinozem/wine-assistant/actions/workflows/release-drafter.yml/badge.svg)](../../actions/workflows/release-drafter.yml)
[![Changelog on Release](https://github.com/glinozem/wine-assistant/actions/workflows/changelog-on-release.yml/badge.svg)](../../actions/workflows/changelog-on-release.yml)

Мини-сервис для поиска вин, хранения прайс-данных и истории цен/остатков.
API на Flask + PostgreSQL (pg_trgm, pgvector), загрузка Excel/CSV.

---

## Содержание

- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
  - [1) Поднять БД](#1-поднять-бд)
  - [1_5) Применить миграции (обязательно)](#15-применить-миграции-обязательно)
  - [2) Создать .env](#2-создать-env)
  - [3) Установить зависимости](#3-установить-зависимости)
  - [4) Загрузить данные](#4-загрузить-данные)
  - [5) Запустить API](#5-запустить-api)
- [API](#api)
  - [/health](#health)
  - [/search](#search)
  - [/catalog/search](#catalogsearch)
  - [/sku/…](#sku)
  - [Swagger / OpenAPI](#swagger--openapi)
- [Логика цен и скидок](#логика-цен-и-скидок)
- [Adminer (SQL UI)](#adminer-sql-ui)
- [Миграции БД](#миграции-бд)
- [ETL / загрузчик](#etl--загрузчик)
- [CI/CD и CHANGELOG](#cicd-и-changelog)
- [Roadmap](#roadmap)

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
# БД: 127.0.0.1:15432 (host) → контейнер db:5432
# Adminer: http://localhost:18080
⚠️ db/init.sql создаёт минимальную схему. Для полной схемы обязательно примените миграции!

1_5) Применить миграции (обязательно)
powershell
Копировать код
# применит все *.sql из db/migrations по алфавиту
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
Миграции добавят:

products.price_list_rub, products.price_final_rub;

историю цен product_prices (+ guardrails: без перекрытий, уникальный индекс);

историю остатков inventory_history и индексы;

актуальную структуру inventory (stock_total, reserved, stock_free);

индексы/расширения (pg_trgm, pgvector, btree_gist и пр.).

2) Создать .env
ini
Копировать код
# .env
PGHOST=127.0.0.1
PGPORT=15432
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db

# API
API_KEY=mytestkey
FLASK_HOST=127.0.0.1
FLASK_PORT=18000
FLASK_DEBUG=1
3) Установить зависимости
powershell
Копировать код
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Для Excel используется openpyxl.

4) Загрузить данные
Используйте единый скрипт scripts/load_csv.py.

Excel (с учётом скидки из S5):

powershell
Копировать код
$FILE="data\inbox\Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx"
python scripts\load_csv.py --excel "$FILE" --asof 2025-01-20 --discount-cell S5 --prefer-discount-cell
CSV (семпл):

powershell
Копировать код
python scripts\load_csv.py --csv data\sample\dw_sample_products.csv
5) Запустить API
powershell
Копировать код
python api\app.py
# или с .env: FLASK_HOST=127.0.0.1, FLASK_PORT=18000
# http://127.0.0.1:18000/health
API
/health
Проверка готовности:

bash
Копировать код
GET /health → { "ok": true }
/search
Поиск в каталоге по финальной цене и полнотексту:

php-template
Копировать код
GET /search?q=<строка>&max_price=<число>&limit=<n>
Фильтр по цене идёт по price_final_rub.

Релевантность — pg_trgm.similarity по search_text (+ fallback по title_en).

limit по умолчанию 10.

/catalog/search
Пагинация + фильтры + наличие:

pgsql
Копировать код
GET /catalog/search?q=&max_price=&color=&region=&style=&grape=&in_stock=(true|false)&limit=20&offset=0
Возвращает { items, total, limit, offset }.
Поле in_stock берётся из таблицы inventory (по умолчанию true, если нет записи).

/sku
Детали товара (требует API-ключ):

vbnet
Копировать код
GET /sku/<code>
Headers: X-API-Key: <ваш ключ>
История цен:

bash
Копировать код
GET /sku/<code>/price-history?limit=...&offset=...
Headers: X-API-Key: <ваш ключ>
История остатков (с датами):

vbnet
Копировать код
GET /sku/<code>/inventory-history?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=...&offset=...
Headers: X-API-Key: <ваш ключ>
Swagger / OpenAPI
/openapi.json — спецификация (если включили).

/docs — Swagger UI (если включили flasgger).

Как включить (опционально):

bash
Копировать код
pip install flasgger
В api/app.py:

python
Копировать код
from flasgger import Swagger
# ...
app = Flask(__name__)
Swagger(app, template_file='openapi.yaml')  # или собрать dict динамически
Логика цен и скидок
price_list_rub — прайс-цена из Excel (столбец «Цена прайс»).

price_final_rub — финальная цена с учётом скидки.

Скидка берётся в порядке приоритета:

из ячейки S5 (верхняя скидка в шапке) — если задана или --prefer-discount-cell;

из «второй строки» заголовка (если там указан %);

из колонки «Цена со скидкой»;

иначе price_final_rub = price_list_rub.

Переменная окружения PREFER_S5=1 или флаг --prefer-discount-cell заставляет приоритетно использовать S5.

Эндпоинт /search фильтрует по price_final_rub.

Adminer (SQL UI)
URL: http://localhost:18080

Внутри docker-сети:

Server: db

User: postgres

Password: dev_local_pw

Database: wine_db

С хоста (psql): 127.0.0.1:15432

Миграции БД
SQL-миграции: db/migrations/*.sql

Прогон:

powershell
Копировать код
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1
Накатывают:

колонки цен в products,

историю цен product_prices (уникальный индекс, запрет перекрытий),

историю остатков inventory_history,

актуальные поля в inventory (stock_total, reserved, stock_free),

индексы и расширения (pg_trgm, btree_gist и пр.).

db/init.sql — минимальная схема для инициализации контейнера.
Для полноценной работы обязательно выполняйте миграции.

ETL / загрузчик
Используйте только scripts/load_csv.py:

Поддерживает Excel и CSV.

Автоопределяет шапку, извлекает скидку из S5, нормализует коды.

Пишет:

products (оба типа цен, атрибуты),

product_prices (история цен),

inventory и inventory_history (остатки/резервы/свободный остаток).

Старый скрипт etl/run_daily.py — deprecated.

CI/CD и CHANGELOG
Release Drafter формирует черновики релизов.

При публикации/редактировании релиза триггерится Changelog on Release:

генерирует CHANGELOG.md;

создаёт авто-PR docs/changelog: <tag>.

Для надёжного авто-PR используем PAT (fine-grained) в secrets.PAT_CREATE_PR.

Бейджи в начале README показывают статусы CI, Release Drafter, Changelog on Release.

Roadmap
 Выравнять db/init.sql с актуальной схемой (чтобы cold-start без миграций тоже работал).

 Покрыть scripts/load_csv.py тестами (минимум happy-path + разбор S5 + конфликтующие цены).

 Вынести CORS (flask-cors) для фронта.

 Полноценная OpenAPI-схема + аннотации у всех эндпоинтов.

 Примеры клиентов (curl/PowerShell, Python requests).

 Метрики (логирование запросов, время ответа), Sentry/OTel (опционально).
