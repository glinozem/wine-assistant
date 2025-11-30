## Расширенное описание PR: wineries, enrichment и новые SKU / history API

### 1. Контекст и цель изменений

Этот Pull Request завершает блок работ по:
- заведению справочника виноделен (`wineries`);
- обогащению каталога продуктов данными о регионе и сайте производителя;
- расширению публичного API под задачи витрины и аналитики:
  - `/api/v1/products/search`
  - `/api/v1/sku/<code>`
  - `/api/v1/sku/<code>/price-history`
  - `/api/v1/sku/<code>/inventory-history`.

Основная идея — **связать боевой прайс-лист, PDF-каталог виноделен и API одного SKU** так,
чтобы фронтенд и внешние интеграции могли получать из одного места:
- актуальную цену и остатки;
- человекочитаемый регион и стиль;
- сайт производителя и русское название винодельни;
- расширенное текстовое описание винодельни для витрины / карточки товара.

---

### 2. Импорт виноделен из PDF-каталога

В рамках PR реализована цепочка для работы с PDF-каталогом виноделен:

1. **Извлечение сырых данных из PDF**
   Скрипт:
   - `scripts/extract_wineries_from_pdf.py`
   Появляется файл:
   - `data/catalog/wineries_enrichment_from_pdf.xlsx`
   (и отладочная версия с `_debug`, где сохраняется колонка `_page`).

2. **Нормализация поставщиков и названий виноделен**
   Скрипт:
   - `scripts/normalize_wineries_suppliers.py`
   На этом шаге:
   - приводим поставщиков к единому значению (`supplier`), которое реально встречается в `products.supplier`;
   - выравниваем русские имена виноделен (`supplier_ru` / `winery_name_ru`);
   - очищаем и чиндим строки сайта (`producer_site`) и региона (`region`).

   Результат:
   - `data/catalog/wineries_enrichment_from_pdf_norm.xlsx` — «чистый» Excel для загрузки в БД.

3. **Загрузка справочника виноделен в БД**
   Скрипт:
   - `scripts/load_wineries.py`
   Использование (боевой режим):

   ```bash
   python -m scripts.load_wineries --excel data/catalog/wineries_enrichment_from_pdf_norm.xlsx --apply
   ```

   Логика:
   - новые винодельни вставляются в таблицу `wineries`;
   - при повторном запуске записи обновляются по ключу `supplier`.

---

### 3. Таблица `wineries` и миграция

В БД появляется таблица `wineries`, которую создаёт миграция:

- `db/migrations/0012_wineries.sql`

Основные поля таблицы:

- `supplier` — ключ для связи с `products.supplier` (латинское имя поставщика/винодельни);
- `supplier_ru` — русское человекочитаемое название;
- `region` — нормализованный регион винодельни (для витрины и фильтров);
- `producer_site` — сайт производителя;
- возможно, дополнительные текстовые поля под описание (в текущей версии фокус на `supplier_ru`, `region`, `producer_site`).

Эта таблица используется как справочник для enrichment и API.

---

### 4. Обогащение `products` по данным справочника `wineries`

#### 4.1. Enrichment продуктов по Excel

Скрипт:

- `scripts/enrich_producers.py`

Задача:
- взять подготовленный Excel со сведениями о винодельнях (`wineries_enrichment.xlsx`);
- обновить в `products` поля:
  - `region`
  - `producer_site`
  - (и потенциально другие дополнительные поля).

Скрипт аккуратно логирует, сколько строк затронуто, и работает поверх уже загруженного прайс-листа.

#### 4.2. Массовое обновление `products.region` и `products.producer_site` через SQL

После загрузки `wineries` выполняются SQL-апдейты:

```sql
UPDATE products p
SET region = w.region
FROM wineries w
WHERE p.supplier = w.supplier
  AND p.region IS NULL
  AND w.region IS NOT NULL;
```

```sql
UPDATE products p
SET producer_site = w.producer_site
FROM wineries w
WHERE p.supplier = w.supplier
  AND p.producer_site IS NULL
  AND w.producer_site IS NOT NULL;
```

Итог:
- у ~2/3 каталога появляется осмысленный регион;
- часть позиций получает сайт производителя из справочника;
- данные становятся более пригодны для витрины и поиска.

---

### 5. Расширение и синхронизация API `/api/v1/products/search`

Эндпоинт:

- `/api/v1/products/search`
- алиас: `/catalog/search`

Основные изменения:

1. **Расширенный SELECT**
   Сейчас в выдачу включаются поля:

   - базовые:
     - `code`, `name`, `producer`, `country`, `region`, `color`, `style`,
     - `grapes`, `vintage`,
     - `price_list_rub`, `price_final_rub`,
     - `stock_total`, `stock_free`,
   - Vivino:
     - `vivino_rating`, `vivino_url`,
   - поставщик/винодельня:
     - `supplier`,
     - `producer_site`,
     - `image_url`,
     - `supplier_ru`,
     - `winery_name_ru`,
     - `winery_description_ru`.

2. **Нормализация числовых полей**
   Функция `_normalize_product_row()` аккуратно приводит только «правильно числовые» поля
   к `number` в JSON (`price_*`, `stock_*`, `vivino_rating`).
   Строки остаются строками — без агрессивного кастинга.

3. **Pydantic-схема для поиска**
   В `api/schemas.py` заведен `ProductSearchItem`, на 100% синхронизированный с SELECT.
   Ответ `/api/v1/products/search` описан через `CatalogSearchResponse`, которая:
   - содержит список `items: list[ProductSearchItem]`;
   - отдаёт `total`, `offset`, `limit`, `query`.

4. **Swagger-описание**
   Докстринг `/catalog/search` обновлён так, чтобы соответствовать новым полям и схеме `CatalogSearchResponse`.
   Это закрывает документацию по поиску по каталогу.

---

### 6. Новый SKU API: `/api/v1/sku/<code>`

Эндпоинт:

- `GET /api/v1/sku/<code>`

Цель:
- Карточка SKU, совмещающая:
  - данные `products`,
  - справочник `wineries`,
  - актуальную цену (последняя запись в `product_prices`).

Основные моменты:

1. **SELECT полностью синхронизирован со схемой**
   В запрос добавлены все поля, которые фактически используются в витрине и тестах:
   - `code`, `name`, `title_ru`,
   - `country`, `region`, `color`, `style`,
   - `grapes`, `vintage`,
   - `price_list_rub`, `price_final_rub`,
   - `stock_total`, `stock_free`,
   - `vivino_rating`, `vivino_url`,
   - `supplier`, `supplier_ru`,
   - `producer_site`,
   - `image_url`,
   - `winery_name_ru`, `winery_description_ru`.

2. **Схема `SkuResponse` в `api/schemas.py`**
   Создана и выровнена со структурой, которую реально возвращает SQL.
   Исправлены типы «проблемных» полей (ранее приводили к 500-кам):

   - `grapes: str | None` (раньше был `int` и падал на строках вроде `"Монастрель"`);
   - `vintage: str | None` (поддержка `NV` и прочих строковых значений);
   - `vivino_rating: float | str | None` (в реальных данных встречаются и числа, и `"-"`);
   - все текстовые поля из виноделен и описаний — строго строки или `None`.

3. **Обработка ошибок**
   - если SKU не найден — возвращается 404, а не 500;
   - все валидационные ошибки Pydantic теперь исключены за счёт корректной схемы.

4. **Интеграция с тестами**
   Эндпоинт используется в интеграционных тестах для проверки:
   - согласованности последних цен между `product_prices` и API;
   - доступности реальных боевых SKU (`D000081`, `D009704` и др.).

---

### 7. History-эндпоинты: price & inventory

Эндпоинты:

- `GET /api/v1/sku/<code>/price-history`
- `GET /api/v1/sku/<code>/inventory-history`

Назначение:
- показывать временной ряд:
  - изменения цен;
  - изменения остатков.

Основные моменты:

1. **Единая базовая модель параметров**
   В `api/schemas.py` добавлен `DateRangeParams` c полями:
   - `from` → `dt_from: date | None`
   - `to` → `dt_to: date | None`
   - `limit`, `offset`

   От него наследуются:
   - `PriceHistoryParams`
   - `InventoryHistoryParams`

   Валидатор проверяет, что `from <= to`.

2. **Схемы ответов**
   Для каждого эндпоинта описаны:
   - элемент истории:
     - `PriceHistoryItem` / `InventoryHistoryItem` (названия условные, в коде — конкретные классы);
   - обёртка:
     - `PriceHistoryResponse`
     - `InventoryHistoryResponse`,
     где есть `items`, `total`, `limit`, `offset`, `code`.

3. **Swagger-описание**
   Докстринги эндпоинтов обновлены и включают:
   - описание query-параметров `from`, `to`, `limit`, `offset`;
   - ссылки на JSON-схемы ответов.

4. **Проверка на живых данных**

   Пример:

   ```http
   GET /api/v1/sku/D000081/price-history?from=2025-01-01&to=2025-12-31&limit=10
   ```

   Возвращает список из двух цен:
   - 20.01.2025 – 03.06.2025;
   - с 03.06.2025 по настоящее время.

---

### 8. Тесты и проверка целостности

1. **Unit-тесты и интеграционные тесты**

   - `164 passed` — весь тестовый набор зелёный.
   - Особый акцент на:
     - `tests/integration/test_api_export_sku_and_price_history.py`
     - `tests/integration/test_price_import_etl.py`
       - `test_latest_price_single_sku_db_and_api_consistent`
       - `test_latest_price_real_skus_db_and_api_consistent`

2. **Ручная проверка API**

   - `/api/v1/products/search?limit=3`
   - `/api/v1/products/search?in_stock=true&limit=5`
   - `/api/v1/sku/D000081`
   - `/api/v1/sku/D000081/price-history?...`

   Результат:
   - карточка SKU отдаёт корректные данные (регион, сайт, описание винодельни);
   - history-эндпоинты отдаёт ожидаемую временную шкалу цен;
   - ошибки на уровне Pydantic устранены.

---

### 9. Обратная совместимость

- Старый `/catalog/search` остаётся рабочим, но теперь использует те же параметры и SELECT, что и `/api/v1/products/search`.
- Формат ответа `/api/v1/products/search` **расширен**, но не поломан:
  - добавлены поля, существующие клиенты могут их игнорировать.
- SKU и history API строятся поверх уже существующих таблиц:
  - `products`
  - `product_prices`
  - `inventory`
  и дополняют функциональность, не ломая текущий экспорт.

---

### 10. Резюме

В этом PR:

- заведена и заполнена таблица `wineries` на основе PDF-каталога;
- реализована цепочка enrichment для `products.region` и `products.producer_site`;
- расширены и синхронизированы API:
  - поиск по каталогу (`/api/v1/products/search`);
  - карточка SKU (`/api/v1/sku/<code>`);
  - история цен и остатков для SKU;
- исправлены типы и схемы Pydantic под реальные данные из БД;
- зелёные 164 теста подтверждают целостность решений.

PR завершает большой блок по связке **прайс-листов, справочника виноделен и SKU API** и готов к ревью и интеграции с UI.
