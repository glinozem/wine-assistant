# Wine Assistant — README (RU)

## 1. Описание проекта

**wine-assistant** — это веб-сервис для работы с винным прайс-листом поставщика.

Основные задачи:

- импорт Excel-прайсов в базу данных (PostgreSQL);
- REST API для поиска по товарам;
- экспорт результатов поиска и карточек SKU в форматы **JSON / XLSX / PDF**;
- экспорт истории изменения цен по отдельному SKU.

Проект предназначен для использования в качестве «прослойки» между сырьём (Excel-файлы поставщика) и конечными потребителями данных (UI, отчёты, интеграции с другими системами).

---

## 2. Технологический стек

- **Backend**: Python, Flask + gunicorn.
- **База данных**: PostgreSQL 16 (образ `pgvector/pgvector:pg16`, работает в Docker).
- **Миграции**: SQL-скрипты в каталоге `db/migrations`.
- **Тесты**: `pytest` (юнит- и интеграционные тесты; интеграционные работают с реальной БД при `RUN_DB_TESTS=1`).
- **Линтер**: `ruff`.
- **Оркестрация**: `docker compose`.

---

## 3. Docker и запуск всех сервисов

### 3.1. Состав docker-compose

В `docker compose`-стеке используются сервисы:

- **wine-assistant-db** — PostgreSQL 16 (`pgvector/pgvector:pg16`), порт: `15432 → 5432`.
- **wine-assistant-api** — Flask-приложение под gunicorn, порт: `18000 → 8000`.
- **wine-assistant-migrator** — однократный контейнер для применения SQL-миграций к БД.
- **wine-assistant-adminer** — Adminer для ручного просмотра БД, порт: `18080 → 8080`.

Окружение настраивается через `.env` (хост, порт, логины/пароли для БД и API-ключи).

### 3.2. Полный цикл: пересборка и запуск

```powershell
# 1. Остановка и полная очистка стека (контейнеры + volume с БД)
docker compose down -v

# 2. Сборка образа API (и зависимостей)
docker compose build

# 3. Подъём всех сервисов
docker compose up -d

# 4. Проверка статуса контейнеров
docker compose ps
```

Ожидается, что:

- `wine-assistant-db` в состоянии **healthy**;
- `wine-assistant-migrator` отработал и завершился (`Exited 0`);
- `wine-assistant-api` и `wine-assistant-adminer` работают (`Up`).

### 3.3. Health-чеки API

```powershell
$baseUrl = "http://localhost:18000"

Invoke-RestMethod "$baseUrl/live"
Invoke-RestMethod "$baseUrl/ready"
Invoke-RestMethod "$baseUrl/health"
```

- `/live` — возвращает JSON со статусом `alive` и временем запуска;
- `/ready` — проверяет доступность БД (статус `ready`);
- `/health` — простой текстовый ответ `"ok"` / `"True"`.

### 3.4. Доступ к БД и логам

Проверить количество записей в таблице `products`:

```powershell
docker compose exec db `
  psql -U postgres -d wine_db -c "SELECT count(*) FROM products;"
```

Посмотреть логи API (например, при отладке экспортов):

```powershell
docker compose logs api | Select-String "export_sku"
docker compose logs api | Select-String "Incoming request"
```

Adminer доступен по адресу: `http://localhost:18080`.

---

## 4. Импорт прайс-листов (ETL)

### 4.1. Скрипт импорта

Импорт выполняется из корня проекта командой:

```bash
python -m scripts.load_csv --excel "путь/к/файлу.xlsx"
```

В логах видно:

- автоопределение даты прайса из имени файла:

  ```text
  [date] Effective date: YYYY-MM-DD (source: auto-extracted)
  ```

- настройки Excel:
  - `sheet=0`
  - `header_row=3` (заголовки в 4-й строке Excel);
- вычисление скидки по ячейке `S5` (пока всегда 0.0):

  ```text
  [discount] header=None cell(S5)=0.0 ... -> used=0.0
  ```

- результат:

  ```text
  [OK] Import completed successfully
     Envelope ID: <uuid>
     Rows processed (good): N
     Rows failed (quarantine): 0
     Effective date: YYYY-MM-DD
  ```

Каждый импорт заносится в «конверт» (envelope); для неудачных строк есть отдельная таблица `quarantine`.

### 4.2. Ожидаемая структура входного Excel

Важно, чтобы в прайсе были, как минимум, следующие столбцы
(по русским заголовкам в рабочем шаблоне):

- **Фото** — картинка бутылки (сейчас используется как исходные данные для возможного поля `image_url`, прямых URL в Excel нет).
- **Код** — артикул / SKU.
- **Vivino** — числовой рейтинг Vivino (например, `4`, `4.3`, `3.9`).
  В БД кладётся в поле `vivino_url` (историческое имя колонки, фактически это «оценка на Vivino»).
- **Рейтинг** — экспертный рейтинг (например `96`, `93`, `94`).
  В БД кладётся в `vivino_rating`.
- **Св-во** — специальные свойства/флаги (в БД: `features`, например `Э`).
- **Страна**, **Категория**, **Наименование**, **Сорт\nвинограда**, **Цвет**, **Тип**,
  **Год урожая**, **Алк., %**, **Ёмк., л**, **Бут. в кор.**,
  **Цена прайс**, **Цена со скидкой**, **остатки**, **резерв**, **свободный остаток**.
- **Поставщик** — поставщик/производитель для отображения в API и отчётах.
- Дополнительно может присутствовать столбец с **сайтом производителя**
  (он попадает в поле `producer_site`).

### 4.3. Массовый импорт из каталога data/inbox (PowerShell)

Пример типового скрипта:

```powershell
$files = @(
  ".\data\inbox\Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_06_03 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_06_25 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_08_06 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_08_19 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_09_29 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_10_22 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_10_27 Прайс_Легенда_Виноделия.xlsx"
)

foreach ($f in $files) {
    Write-Host ">>> Импорт $f"
    python -m scripts.load_csv --excel $f
}
```

После успешного импорта можно проверить количество товаров в БД:

```powershell
docker compose exec db `
  psql -U postgres -d wine_db -c "SELECT count(*) FROM products;"
```

---

## 5. Модель в БД (ключевые поля products)

В таблице `products` хранятся, помимо старых полей, следующие:

- `code` — артикул / SKU;
- `title_ru` — наименование вина;
- `grapes` — сортовой состав (из столбца «Сорт винограда»);
- `vintage` — год урожая;
- `vivino_url` — рейтинг Vivino (число `4.2` и т.п., историческое имя колонки);
- `vivino_rating` — экспертный рейтинг (число `96` и т.п.);
- `supplier` — поставщик (как в прайсе);
- `features` — флаги (например `Э`);
- `producer_site` — сайт производителя (если присутствует в Excel);
- `image_url` — ссылка/путь к фото бутылки (пока не заполняется автоматически; выводится в отчётах как отдельная колонка и поле).

Также при импорте учтён `FutureWarning` от pandas: цены приводятся к числу
через `to_numeric` / `astype(float)` перед сохранением в DataFrame.

---

## 6. API и служебные эндпоинты

### 6.1. Служебные эндпоинты

- `GET /live` — проверка «живости» приложения (возвращает JSON с `status=alive` и временем старта).
- `GET /ready` — проверка готовности (доступности БД) — JSON с `status=ready`.
- `GET /health` — простой текстовый ответ `"ok"` / `"True"` для внешнего мониторинга.

---

## 7. Поиск по товарам

### 7.1. Эндпоинт поиска

`GET /api/v1/products/search`

Параметры (основные):

- `limit` — ограничение на количество записей;
- `offset` — смещение;
- `in_stock` — фильтр по наличию на складе;
- дополнительные параметры фильтрации и сортировки см. в `validation.py`.

Пример запроса (PowerShell):

```powershell
$baseUrl = "http://localhost:18000"

Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=3&in_stock=true" `
  | ConvertTo-Json -Depth 5
```

Упрощённый пример ответа:

```json
{
  "items": [
    {
      "code": "D010210",
      "name": "Delampa Monastrell Делампа Монастрель",
      "country": "Испания",
      "color": "красное",
      "style": "DOP",
      "price_list_rub": 1860,
      "price_final_rub": 1860,
      "stock_free": 12334,
      "stock_total": 12502,
      "producer": null,
      "region": null,
      "grapes": "Монастрель",
      "vintage": 2023,
      "vivino_url": "3.9",
      "vivino_rating": null,
      "supplier": "Bodegas Delampa, S.L.",
      "producer_site": "https://example.com",
      "image_url": null
    }
  ],
  "limit": 3,
  "offset": 0,
  "query": null,
  "total": 3
}
```

Важно: в API поле `vivino_url` — это **рейтинг Vivino**, а не URL.

---

## 8. Экспорт данных

### 8.1. Экспорт поиска

Эндпоинт:

```text
GET /export/search?format=json|xlsx|pdf
```

Часть вызовов может быть защищена API-ключом (`X-API-Key`), в зависимости от настроек окружения.

#### 8.1.1. JSON

Пример:

```powershell
Invoke-RestMethod "$baseUrl/export/search?format=json&limit=5&in_stock=true" `
  | ConvertTo-Json -Depth 5
```

Структура:

```json
{
  "Count": 5,
  "value": [
    {
      "code": "D010036",
      "title_ru": "47 Anno Domini, "Le Argille" Cabernet di Cabernet ...",
      "country": "Италия",
      "color": "красное",
      "style": "IGP",
      "price_list_rub": 9909,
      "price_final_rub": 9909,
      "stock_free": 133,
      "stock_total": 133,
      "region": null,
      "producer": null,
      "grapes": "Каберне Совиньон- 50%, Каберне Фран- 50%",
      "vintage": 2018,
      "vivino_url": "4.4",
      "vivino_rating": null,
      "supplier": "Tombacco",
      "producer_site": "https://www.rinomatatombacco.it",
      "image_url": null
    }
  ]
}
```

#### 8.1.2. XLSX

Пример:

```powershell
Invoke-WebRequest `
  "$baseUrl/export/search?format=xlsx&limit=100&in_stock=true" `
  -OutFile ".\wines_with_photos.xlsx"
```

Первая строка — заголовки. Порядок колонок:

1. Код → `code`
2. Название → `title_ru`
3. Цена прайс → `price_list_rub`
4. Цена финальная → `price_final_rub`
5. Цвет → `color`
6. Регион → `region`
7. Производитель → `producer`
8. Сортовой состав → `grapes`
9. Год урожая → `vintage`
10. Рейтинг Vivino → `vivino_url`
11. Экспертный рейтинг → `vivino_rating`
12. Поставщик → `supplier`
13. Сайт производителя → `producer_site`
14. Фото (URL) → `image_url` (пока пусто, т.к. ссылки на фото не загружаются из Excel автоматически).

#### 8.1.3. PDF (табличный отчёт по поиску)

Пример:

```powershell
Invoke-WebRequest `
  "$baseUrl/export/search?format=pdf&limit=30&in_stock=true" `
  -OutFile ".\wines.pdf"
```

В отчёте:

- шапка с датой формирования и количеством позиций;
- таблица с теми же колонками, что и в XLSX (`Код`, `Название`, `Цена прайс`, …, `Поставщик`, `Сайт производителя`, `Фото (URL)`);
- для пустых значений используются прочерки или пустые ячейки.

---

### 8.2. Экспорт по конкретному SKU

Эндпоинт:

```text
GET /export/sku/<code>?format=json|pdf
```

Требуется API-ключ (`X-API-Key`).
Если ключ не передан → `{"error": "forbidden"}`.
Если SKU не найден → `{"error": "not_found"}`.

#### 8.2.1. JSON (PowerShell, с учётом синтаксиса)

Ключевой момент в PowerShell: при формировании URL с параметром `?format=...`
нужно оборачивать переменную SKU в `$()`:

```powershell
$baseUrl = "http://localhost:18000"
$apiKey  = "ВАШ_API_КЛЮЧ"
$headers = @{ "X-API-Key" = $apiKey }
$sku     = "D011402"

$exportUrl = "$baseUrl/export/sku/$($sku)?format=json"

$exportUrl
# http://localhost:18000/export/sku/D011402?format=json

Invoke-RestMethod $exportUrl -Headers $headers `
  | ConvertTo-Json -Depth 5
```

Упрощённый пример ответа:

```json
{
  "code": "D011402",
  "title_ru": "Champagne Pinot-Chevauchet Joyeuse Brut Шампань Пино-Шевоше Жуайёз Брют",
  "name": "Champagne Pinot-Chevauchet Joyeuse Brut Шампань Пино-Шевоше Жуайёз Брют",
  "country": "Франция",
  "color": "белое",
  "style": "AOP",
  "price_list_rub": 7056,
  "price_final_rub": 7056,
  "stock_free": 191,
  "stock_total": 191,
  "region": null,
  "producer": null,
  "grapes": "80 % Менье 20% Шардонне",
  "vintage": 2018,
  "vivino_url": "4",
  "vivino_rating": null,
  "supplier": "Pinot-Chevauchet",
  "producer_site": "https://champagne-pinotchevauchet.com",
  "image_url": null
}
```

Обратите внимание:

- `title_ru` всегда присутствует вместе с `name`, чтобы структура была совместима с `/api/v1/products/search`;
- `producer_site` и `image_url` возвращаются, если есть в БД;
- числовые поля остатков и цен приводятся к числам (а не к строкам).

#### 8.2.2. PDF-карточка SKU

Пример:

```powershell
Invoke-WebRequest `
  -Uri "$baseUrl/export/sku/$($sku)?format=pdf" `
  -Headers $headers `
  -OutFile ".\card_$sku.pdf"
```

Если запрос сделан без `X-API-Key` или с некорректным SKU, будет JSON с ошибкой.

В PDF отображаются:

- название вина (русское) крупным шрифтом;
- страна / регион / категория (стиль);
- цвет, сортовой состав, год урожая;
- цена прайс / финальная;
- остатки (общий и свободный);
- поставщик (`supplier`);
- сайт производителя (`producer_site`);
- рейтинг Vivino (из `vivino_url`, форматируется как числовое значение, например `4.0`);
- экспертный рейтинг (из `vivino_rating`, если есть);
- поле «Фото (URL)» — пока прочерк, т.к. `image_url` не заполнено.

---

### 8.3. Экспорт истории цен

Эндпоинт:

```text
GET /export/price-history/<code>?format=xlsx
```

Также требует `X-API-Key`.

Пример:

```powershell
Invoke-WebRequest `
  "$baseUrl/export/price-history/$($sku)?format=xlsx" `
  -Headers $headers `
  -OutFile ".\price_history_$sku.xlsx"
```

В XLSX-файле содержится история изменений цен по датам:

- дата (`effective_date`);
- цена прайс;
- цена финальная;
- прочие поля, связанные с импортами.

Числовые поля приводятся к `float`, предупреждения pandas обработаны.

---

## 9. Тесты и качество кода

### 9.1. Запуск тестов (PowerShell)

Для прогонов с реальной БД:

```powershell
$env:RUN_DB_TESTS = "1"
pytest -q -rs
```

- `RUN_DB_TESTS=1` включает интеграционные тесты, которые стучатся в реальную БД в Docker;
- без этого переменная окружения интеграционные тесты, завязанные на БД, могут быть пропущены.

Результат на актуальной версии проекта:

- **164 passed, 0 failed**.

### 9.2. Линтер

```bash
ruff check .
# либо с автофиксами
ruff check . --fix
```

На текущий момент:

- `ruff check .` не выдаёт ошибок.

---

## 10. Полный сценарий «с нуля до зелёных тестов»

```powershell
# 1. Поднять весь стек в Docker
docker compose down -v
docker compose build
docker compose up -d

# 2. Проверить, что API жив и готов
$baseUrl = "http://localhost:18000"
Invoke-RestMethod "$baseUrl/live"
Invoke-RestMethod "$baseUrl/ready"
Invoke-RestMethod "$baseUrl/health"

# 3. Импортировать все прайс-листы из data/inbox
$files = @(
  ".\data\inbox\Копия 2025_01_20 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_06_03 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_06_25 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_08_06 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_08_19 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_09_29 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_10_22 Прайс_Легенда_Виноделия.xlsx",
  ".\data\inbox5_10_27 Прайс_Легенда_Виноделия.xlsx"
)

foreach ($f in $files) {
    Write-Host ">>> Импорт $f"
    python -m scripts.load_csv --excel $f
}

# 4. Проверить, что в products появились данные
docker compose exec db `
  psql -U postgres -d wine_db -c "SELECT count(*) FROM products;"

# 5. Прогнать тесты
$env:RUN_DB_TESTS = "1"
pytest -q -rs
```

После выполнения этих шагов:

- база заполнена актуальными данными из прайсов;
- API отвечает на запросы поиска и экспортов;
- все юнит- и интеграционные тесты зелёные.
