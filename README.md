Wine Assistant

Мини-сервис для работы с ассортиментом и ценами вин: загрузка Excel/CSV, хранение истории цен и остатков, быстрый поиск по каталогу, простой HTTP API (Flask) поверх PostgreSQL (pg_trgm, pgvector).

Содержание

Возможности

Требования

Быстрый старт

1) Переменные окружения

2) Запуск Docker (Postgres + Adminer)

3) Миграции

4) Загрузка данных (Excel/CSV)

5) Запуск API

API

Схема данных

Трюки для Windows/PowerShell

Разработка и качество

Changelog

Возможности

Две цены в products: price_list_rub (прайс) и price_final_rub (фактическая) + обратная совместимость со старым price_rub.

История цен: таблица product_prices с уникальностью (code, effective_from), защитой от перекрытий периодов (GiST + tstzrange) и чеком на неотрицательные цены.

История остатков: inventory_history + удобная функция upsert_inventory(...) для апсерта текущего состояния и логирования истории.

Поиск: pg_trgm по search_text (GIN-индекс), фильтры по цвету/региону/стилю, ограничение по финальной цене, fallback по title_en для латиницы.

Безопасность API: защищённые эндпоинты с заголовком X-API-Key.

Утилиты: скрипт миграций scripts/migrate.ps1, надёжный загрузчик Excel/CSV scripts/load_csv.py.

Adminer: веб-клиент БД из коробки.

Требования

Docker Desktop (Windows/macOS/Linux)

Python 3.10+ (для запуска скриптов)

PowerShell (Windows) — команды ниже рассчитаны именно на PowerShell

Быстрый старт
1) Переменные окружения

Скопируйте .env.example → .env и заполните секреты (локально можно оставить дефолты):

PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=dev_local_pw
PGDATABASE=wine_db
TZ=Europe/Helsinki

# Защита API-эндпоинтов (опционально локально, обязательно в prod)
API_KEY=CHANGE_ME

# Управляет debug-режимом Flask
FLASK_DEBUG=0


На Windows часто порты 5432/8080 заняты системными службами. В репозитории уже есть вариант маппинга на 15432 (Postgres) и 18080 (Adminer) через docker-compose.yml. Используйте их при подключении.

2) Запуск Docker (Postgres + Adminer)
docker compose up -d
docker compose ps
# Должно показать:
# wine_assistant-db-1        ...  127.0.0.1:15432->5432/tcp
# wine_assistant-adminer-1   ...  127.0.0.1:18080->8080/tcp


Проверка доступности БД:

docker compose exec db psql -U postgres -d wine_db -c "SELECT 1 as ok;"


Adminer: http://127.0.0.1:18080

(Сервер: db или 127.0.0.1:15432, пользователь: postgres, БД: wine_db)

3) Миграции

Выполнить все SQL-файлы из db/migrations:

powershell -ExecutionPolicy Bypass -File .\scripts\migrate.ps1


Проверка диагностики (опционально):

Get-Content db\migrations\2025-10-14-diagnostics.sql -Raw |
  docker compose exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -f -


Ожидаемые проверки:

ux_product_prices_code_from существует

product_prices_no_overlap (защита перекрытий) и chk_product_prices_nonneg (цена ≥ 0) на месте

перекрытий интервалов нет, отрицательных цен нет

индекс idx_inventory_history_code_time существует

4) Загрузка данных (Excel/CSV)

Установите переменные окружения для подключения скриптов:

$env:PGHOST="127.0.0.1"
$env:PGPORT="15432"
$env:PGUSER="postgres"
$env:PGPASSWORD="dev_local_pw"
$env:PGDATABASE="wine_db"


Excel (пример с прайс-файлом, дата среза и ячейка скидки S5):

$FILE="D:\path\to\Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx"
python scripts\load_csv.py --excel "$FILE" --asof 2025-01-20 --discount-cell S5 --prefer-discount-cell


Скрипт автоматически определит шапку, найдёт ключевые колонки (Код, Наименование, Сорт винограда, Алк.,%, Ёмк.,л, Бут. в кор., Цена прайс, Цена со скидкой, остатки/резерв/свободный остаток, Страна и пр.).

Если в файле есть процент скидки в ячейке (например, S5) или отдельная колонка — скрипт посчитает price_final_rub.

В БД будут обновлены products (включая price_list_rub, price_final_rub) и записана история в product_prices и inventory_history.

CSV:

python scripts\load_csv.py --csv data\sample\dw_sample_products.csv --sep "," --asof 2025-01-20


У ключевого кода товара не должно быть пробелов/кириллицы. Скрипт нормализует код, а при конфликте gracefully обновит запись.

5) Запуск API
$env:FLASK_DEBUG="1"
$env:FLASK_HOST="127.0.0.1"
$env:FLASK_PORT="18000"
$env:API_KEY="mytestkey"
python api\app.py


Проверка:

curl "http://127.0.0.1:18000/health"

API

Базовый URL по умолчанию: http://127.0.0.1:18000

В некоторых эндпоинтах требуется заголовок X-API-Key: <ваш_ключ>.

GET /health

Проверка живости.

{"ok": true}

GET /sku/<code> (требуется X-API-Key)

Возвращает карточку товара, включая обе цены и текущую активную цену из истории:

curl.exe -H "X-API-Key: mytestkey" "http://127.0.0.1:18000/sku/D009704"


Ответ (пример):

{
  "code": "D009704",
  "title_ru": "Il Rocchin Gavi Иль Роккин Гави",
  "title_en": "Gavi",
  "country": "Италия",
  "color": "БЕЛОЕ",
  "style": "тихое",
  "grapes": "Кортезе",
  "abv": "0.12",
  "volume": "0.75",
  "pack": "12.0",
  "price_list_rub": "2778.0",
  "price_final_rub": "2778.0",
  "price_rub": "2778.0",
  "current_price": "2778.0"
}

GET /search

Параметры:

q — строка поиска (рус/латиница; для латиницы есть fallback по title_en)

Фильтры: max_price (по финальной цене), color, region, style, limit (по умолчанию 10)

Пример:

curl "http://127.0.0.1:18000/search?q=Гави&max_price=4000&limit=5"
curl "http://127.0.0.1:18000/search?q=gavi&max_price=4000&limit=5"


Поиск использует pg_trgm по search_text с порогом, плюс сортировка по similarity и fallback ILIKE по title_en для латиницы.

GET /catalog/search

Расширенный поиск с пагинацией и остатками. Параметры:

те же, что в /search, плюс

grape, in_stock (true|false), offset (пагинация)

GET /sku/<code>/price-history

Параметры: limit, offset. Возвращает историю из product_prices.

GET /sku/<code>/inventory-history

Параметры: from, to (YYYY-MM-DD), limit, offset. Данные из inventory_history.

Схема данных
products

Основное описание (код, названия, страна/регион, цвет/стиль, сорт, крепость, объём, упаковка)

Цены: price_list_rub (прайс), price_final_rub (фактическая). Сохраняется и старое поле price_rub.

Индексы: btree по ценам, GIN (search_text gin_trgm_ops) для поиска.

product_prices

Поля: code, price_rub, effective_from, effective_to.

Ограничения:

CHECK (price_rub >= 0)

UNIQUE (code, effective_from)

EXCLUDE USING gist (...) — защита от перекрытия интервалов для одного code.

Утилиты: upsert_price(code, price, timestamp) (есть перегрузка для timestamptz).

inventory / inventory_history

inventory — текущее состояние: stock_total, reserved, stock_free.

inventory_history — история, поле as_of (timestamp), индекс (code, as_of DESC).

Утилита: upsert_inventory(code, stock_total, reserved, stock_free, as_of) — апсерт текущего + запись в историю.

Трюки для Windows/PowerShell

Порты заняты / “forbidden by its access permissions” — используйте маппинг портов в docker-compose.yml на 127.0.0.1:15432 (PG) и 127.0.0.1:18080 (Adminer).

curl vs PowerShell — в PowerShell curl — это алиас Invoke-WebRequest. Для чистого curl используйте curl.exe.
Пример заголовков:

# Чистый curl
curl.exe -H "X-API-Key: mytestkey" "http://127.0.0.1:18000/sku/D009704"

# PowerShell-стиль
Invoke-RestMethod "http://127.0.0.1:18000/sku/D009704" -Headers @{ "X-API-Key" = "mytestkey" }


Юникод в консоли:

chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Разработка и качество

pre-commit: merge-conflicts check, end-of-file-fixer, trim-trailing-whitespace, гвард секрета.
Если end-of-file-fixer что-то поправил — просто git add и повторить коммит.

Ветвление/PR: защита ветки master — Require PR, Require status checks, Block force pushes.

Безопасность: не коммитим .env, ключи — только через переменные окружения/секреты CI.

CORS / OpenAPI (опционально):

CORS: pip install flask-cors, затем в api/app.py:

from flask_cors import CORS
CORS(app)


OpenAPI/Swagger: flasgger или connexion — можно добавить позже.

Changelog
2025-10-14

DB: добавлены price_list_rub и price_final_rub в products.

История цен: product_prices + уникальный индекс (code, effective_from) и защита от перекрытий интервалов (GiST + tstzrange), чек на неотрицательные цены.

История остатков: inventory_history + функция upsert_inventory(...), индекс (code, as_of DESC).

API:

GET /sku/{code} — теперь отдаёт обе цены + current_price (по истории).

GET /sku/{code}/price-history

GET /sku/{code}/inventory-history

Поиск учитывает price_final_rub, добавлен fallback по title_en для латиницы.

Скрипты:

scripts/migrate.ps1 — применяет все миграции из db/migrations.

Улучшен scripts/load_csv.py: чтение Excel/CSV, поддержка скидки (ячейка и/или колонка), апсерты цен/остатков.

Диагностика: db/migrations/2025-10-14-diagnostics.sql.

2025-10-12

Базовый стек: Postgres 16 (pgvector, pg_trgm), Adminer.

Начальные таблицы и загрузка демо-CSV.

Первый вариант API (/health, /search, /sku/{code}).

Test changelog entry
