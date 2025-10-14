Wine Assistant

Мини-сервис для загрузки и поиска ассортимента вина: хранит карточки товаров, две цены (прайс и конечную), историю изменения цен и остатков, и предоставляет HTTP API для поиска и просмотра.

Содержание

Быстрый старт

Переменные окружения

Docker: Postgres + Adminer

Миграции

Загрузка данных (Excel/CSV)

API

/health

/sku/{code}

/sku/{code}/price-history

/sku/{code}/inventory-history

/search

/catalog/search

Индексы и производительность

Безопасность и CORS

Трюки Windows / PowerShell

Тесты / Диагностика данных

Миграции: как добавлять новые

Быстрый старт
# 1) Клонируем и готовим окружение
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant
copy .env.example .env
# отредактируй .env (см. раздел ниже)

# 2) Поднимаем БД и Adminer (локальные порты 15432 и 18080)
docker compose up -d

# 3) Применяем миграции (все .sql из db/migrations)
powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1

# 4) (Опц.) загрузка демонстрационных данных
python scripts\load_csv.py --csv data\sample\dw_sample_products.csv

# 5) Запускаем API (локально)
$env:FLASK_DEBUG="1"
$env:FLASK_HOST="127.0.0.1"
$env:FLASK_PORT="18000"
python api\app.py

# Проверка
curl http://127.0.0.1:18000/health

Переменные окружения

Файл .env:

PGHOST=127.0.0.1
PGPORT=15432          # см. docker-compose (порт контейнера 5432 проброшен на 15432)
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db
TZ=Europe/Helsinki

# Опционально: защита приватных эндпоинтов
API_KEY=mytestkey

# Параметры запуска Flask
FLASK_DEBUG=1
FLASK_HOST=127.0.0.1
FLASK_PORT=18000

Docker: Postgres + Adminer

Используем образ pgvector/pgvector:pg16 (расширения vector, pg_trgm доступны).

Порты по умолчанию (Windows-friendly):

Postgres: 127.0.0.1:15432 -> 5432

Adminer: 127.0.0.1:18080 -> 8080

Вход в Adminer: http://127.0.0.1:18080

System: PostgreSQL, Server: db, User: postgres, Password: dev_local_pw, Database: wine_db

Полезное:

# Полный ресет БД
docker compose down -v
docker compose up -d

Миграции

Все миграции лежат в db/migrations/*.sql. Запуск:

powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1


Что уже есть:

Две цены в products: price_list_rub (прайсовая) и price_final_rub (фактическая).

История цен product_prices с ограничением без перекрытий интервалов (GiST + tstzrange) и проверкой «цена не отрицательная».

История остатков inventory_history и функция upsert_inventory(...).

Индексы для поиска/фильтров.

Диагностика:

Get-Content db\migrations\2025-10-14-diagnostics.sql -Raw |
  docker compose exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -f -

Загрузка данных (Excel/CSV)

Скрипт: scripts/load_csv.py
Возможности:

Чтение Excel (--excel) или CSV (--csv).

Авто-определение разделителя CSV; для Excel — автоматический поиск шапки (строка заголовков).

Поддержка двух цен: "Цена прайс" → price_list_rub, "Цена со скидкой" → price_final_rub.
Если «скидочная» пустая, но задан процент скидки — вычисляется.

История цен обновляется через upsert_price(...).

Запись текущих остатков + лог в inventory_history через upsert_inventory(...).

Примеры:

# CSV
python scripts\load_csv.py --csv data\sample\dw_sample_products.csv

# Excel (лист авто, но можно явно sheet по имени/индексу)
$FILE="D:\...\data\inbox\Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx"
python scripts\load_csv.py --excel "$FILE" --asof 2025-01-20

# Excel с указанием ячейки скидки (в шапке), и приоритетом её над колонкой
python scripts\load_csv.py --excel "$FILE" --asof 2025-01-20 `
  --discount-cell S5 --prefer-discount-cell


Колонки (авто-маппинг):
code, country, title_ru, grapes, abv, volume, pack,
price_list_rub, price_final_rub, stock_total, reserved, stock_free.

API

Сервис стартует на http://127.0.0.1:${FLASK_PORT} (по умолчанию 18000).
JSON — UTF-8 без \uXXXX.

Приватные эндпоинты требуют заголовок X-API-Key: ${API_KEY} (если API_KEY задан).

GET /health

Проверка живости.

curl http://127.0.0.1:18000/health

GET /sku/{code}

Карточка товара + «текущая» цена (последняя открытая в product_prices).

Заголовок: X-API-Key: mytestkey (если включено).

curl -H "X-API-Key: mytestkey" \
  "http://127.0.0.1:18000/sku/D009704"


Ответ включает: price_list_rub, price_final_rub, current_price, и основные поля товара.

GET /sku/{code}/price-history

История изменения цен.

Параметры: limit, offset.

curl -H "X-API-Key: mytestkey" \
  "http://127.0.0.1:18000/sku/D009704/price-history?limit=5"

GET /sku/{code}/inventory-history

История остатков за период.

Параметры: from, to (ISO YYYY-MM-DD), limit, offset.

curl -H "X-API-Key: mytestkey" \
  "http://127.0.0.1:18000/sku/D009704/inventory-history?from=2025-01-01&to=2025-12-31&limit=5"

GET /search

Поиск по каталогу (короткая выборка). Использует price_final_rub для фильтра max_price.
Сортировка — по pg_trgm.similarity(p.search_text, q) (порог 0.1),
fallback: если запрос латиницей, добавляем ILIKE по title_en.

Параметры:
q, max_price, color, region, style, limit (по умолчанию 10).

curl "http://127.0.0.1:18000/search?q=Гави&max_price=3500&limit=5"
curl "http://127.0.0.1:18000/search?q=gavi&max_price=3500&limit=5"

GET /catalog/search

Расширенный поиск + пагинация + флаги наличия.

Параметры:
q, max_price, color, region, style, grape, in_stock (true/false), limit (20), offset (0).

curl "http://127.0.0.1:18000/catalog/search?q=gavi&color=БЕЛОЕ&max_price=4000&limit=5&offset=0"


Ответ: { items: [...], total, limit, offset }.

Индексы и производительность

GIN (pg_trgm) на products.search_text.

BTREE на products.price_list_rub, products.price_final_rub.

История цен:

UNIQUE (code, effective_from) — ux_product_prices_code_from

GiST-ограничение без перекрытий интервалов по (code, [effective_from, effective_to)).

История остатков:

BTREE (code, as_of DESC).

Безопасность и CORS

Если в .env задан API_KEY, эндпоинт /sku/* и истории требуют заголовок X-API-Key.

Если фронт будет на другом домене, добавь CORS:

pip install flask-cors


В api/app.py:

from flask_cors import CORS
CORS(app)

Трюки Windows / PowerShell

curl в PowerShell — это Invoke-WebRequest. Для «настоящего» curl используй curl.exe.

Пример с заголовками:

Invoke-WebRequest "http://127.0.0.1:18000/sku/D009704" -Headers @{ "X-API-Key"="mytestkey" } | Select -Expand Content


Для корректного вывода русских символов:

chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Тесты / Диагностика данных

Диагностика миграций/ограничений/индексов:

Get-Content db\migrations\2025-10-14-diagnostics.sql -Raw |
  docker compose exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -f -


Пример точечной записи в историю остатков (ручная проверка):

SELECT upsert_inventory('D009704', 120.0, 15.0, 105.0, '2025-02-01'::timestamp);

Миграции: как добавлять новые

Создай файл db/migrations/YYYY-MM-DD-topic.sql (UTF-8).

Положи в него DDL/DML, которые должны выполняться идемпотентно
(IF NOT EXISTS, CREATE OR REPLACE FUNCTION, проверяй существование индексов/констрейнтов).

Запусти все миграции:

powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1


Проверь диагностический скрипт.

Лицензия

MIT
