# Поля `producer_site` и `image_url` в Wine Assistant

В прайс-листах поставщика могут появляться дополнительные поля, связанные с производителем и изображением товара:

- **Сайт производителя** — URL официального сайта винодельни / бренда.
- **Фото** — картинка бутылки (этикетка), может храниться как URL или как путь к файлу.

В базе данных эти поля сохраняются в таблицу `products`:

- `producer_site` — сайт производителя.
- `image_url` — ссылка/путь к изображению бутылки.

## Импорт из Excel

Если в Excel-прайсе присутствуют соответствующие столбцы (например, «Сайт производителя» и «Фото»), значения из них попадают в поля:

- `producer_site` → `products.producer_site`
- `image_url` → `products.image_url`

Если колонок нет или ячейки пустые — в БД и в API значение будет `NULL` (в JSON — `null`).

## API

Полей `producer_site` и `image_url` придерживаются основные JSON-эндпоинты.

### `GET /api/v1/products/search`

Публичный эндпоинт (без API-ключа). В каждом элементе `items[*]` присутствуют поля `producer_site` и `image_url`:

```json
{
  "code": "D010210",
  "name": "Delampa Monastrell Делампа Монастрель",
  "country": "Испания",
  "color": "красное",
  "style": "DOP",
  "grapes": "Монастрель",
  "vintage": 2023,
  "price_list_rub": 1860,
  "price_final_rub": 1860,
  "stock_free": 12334,
  "stock_total": 12502,
  "vivino_url": "3.9",
  "vivino_rating": null,
  "supplier": "Bodegas Delampa, S.L.",
  "producer_site": null,
  "image_url": null
}
```

### `GET /api/v1/sku/<code>`

Требует заголовок `X-API-Key`. Возвращает карточку SKU с теми же полями, включая `producer_site` и `image_url`:

```json
{
  "code": "D011402",
  "name": "Champagne Pinot-Chevauchet Joyeuse Brut ...",
  "country": "Франция",
  "color": "белое",
  "style": "AOP",
  "grapes": "80 % Менье 20% Шардонне",
  "vintage": 2018,
  "price_list_rub": 7056,
  "price_final_rub": 7056,
  "stock_total": 191,
  "stock_free": 191,
  "supplier": "Pinot-Chevauchet",
  "vivino_url": "4",
  "vivino_rating": null,
  "producer_site": null,
  "image_url": null
}
```

Числовые поля (`price_list_rub`, `price_final_rub`, `stock_total`, `stock_free`) нормализованы и отдаются как числа, а не строки.

### `GET /export/sku/<code>?format=json`

Также требует `X-API-Key`. В JSON-ответ включены те же поля `producer_site` и `image_url`, а также `title_ru` для отображения:

```json
{
  "code": "D011402",
  "title_ru": "Champagne Pinot-Chevauchet Joyeuse Brut ...",
  "name": "Champagne Pinot-Chevauchet Joyeuse Brut ...",
  "country": "Франция",
  "color": "белое",
  "style": "AOP",
  "grapes": "80 % Менье 20% Шардонне",
  "vintage": 2018,
  "price_list_rub": 7056,
  "price_final_rub": 7056,
  "stock_total": 191,
  "stock_free": 191,
  "supplier": "Pinot-Chevauchet",
  "vivino_url": "4",
  "vivino_rating": null,
  "producer_site": null,
  "image_url": null
}
```

## Отчёты (XLSX/PDF)

На данный момент:

- `producer_site` и `image_url` **не добавлены** в табличные отчёты поиска (`/export/search?format=xlsx|pdf`) и в PDF-карточку SKU.
- Эти поля уже доступны в JSON-экспортах и могут использоваться в UI (ссылка на сайт, превью картинки).

Планируется:

- добавить отображение `producer_site` и `image_url` в PDF-карточку SKU;
- при необходимости — расширить XLSX/PDF-шаблоны отчётов для внутреннего использования.
