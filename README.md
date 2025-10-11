# Wine Sales Assistant — Starter Kit (Step-by-step)

Этот набор — минимальный рабочий каркас: Postgres+pg_trgm, ETL из Excel/CSV, API-поиск.
Ниже — пошаговые действия для Windows 11 + Docker Desktop + Python 3.11.

## 0) Установите зависимости
- Docker Desktop (включите WSL2).
- Python 3.11, pip.
- Git (опционально).

## 1) Запуск базы данных
В терминале PowerShell в папке проекта:
```powershell
docker compose up -d
```
Это поднимет `Postgres:16` и `Adminer` на http://localhost:8080.
БД и таблицы создадутся из `db/init.sql` (расширения pg_trgm, vector; таблицы products, product_prices, inventory).

## 2) Настройка окружения
Скопируйте `.env.example` в `.env` и отредактируйте при необходимости.

## 3) Установка Python-зависимостей
```powershell
pip install -r requirements.txt
```

## 4) Загрузка примера данных (для проверки)
```powershell
python scripts/load_csv.py --csv data/sample/dw_sample_products.csv
```

## 5) Запуск API
```powershell
set FLASK_DEBUG=1
python api/app.py
```
Откройте: http://localhost:8000/health → `{ "ok": true }`
Пробные запросы:
- `http://localhost:8000/sku/D011283`
- `http://localhost:8000/search?q=венето%20совиньон&max_price=3000&color=БЕЛОЕ`
- `http://localhost:8000/catalog/search?color=БЕЛОЕ&region=Венето&max_price=3000&limit=10&offset=0`

## 6) Ежедневный ETL из Excel
Положите актуальный прайс в `data/inbox/Прайс_YYYY-MM-DD.xlsx`. Затем:
```powershell
python etl/run_daily.py --xlsx "data/inbox/Прайс_YYYY-MM-DD.xlsx"
```
Скрипт определит нужные колонки (или возьмёт подсказки из `etl/mapping_template.json`), нормализует данные, выполнит UPSERT в `products` и обновит историю цен.

## 7) Частые вопросы
- **Как указать лист Excel?** `--sheet "Основной"`
- **Как проверить маппинг?** Откройте `etl/mapping_template.json` и подставьте точные имена колонок.
- **Где смотреть БД?** Adminer: System=PostgreSQL, Server=host.docker.internal, User=postgres, Password=postgres, DB=wine_db.

## 8) Дальше
- Добавить Telegram-бота, который дергает `/search` и `/sku`.
- Добавить индексацию векторных эмбеддингов и rerank — позже, после запуска MVP.
