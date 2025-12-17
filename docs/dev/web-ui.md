# Web UI (витрина) — /ui

## Назначение
UI предназначен для быстрой витрины каталога:
- поиск/фильтрация SKU
- просмотр карточки SKU
- просмотр истории цен и остатков (если endpoint доступен)
- отображение картинки SKU (из `image_url` либо через `/sku/<CODE>/image`)

## Где лежит и как отдаётся
- Шаблон: `api/templates/ui.html`
- URL: `GET /ui` (отдаёт HTML страницей)

Важно: UI должен работать «на том же хосте», что и API, поэтому в коде UI используются относительные пути.

## Авторизация
UI поддерживает заголовок:
- `X-API-Key: <key>`

Ключ вводится в UI и сохраняется локально в браузере через `localStorage` под ключом:
- `wine_assistant_api_key`

## API, которые использует UI
- Поиск:
  - `GET /api/v1/products/search?limit=<N>&offset=<M>&in_stock=true|false&q=...&country=...&region=...`
- Карточка SKU:
  - `GET /api/v1/sku/<CODE>`
- История цен:
  - `GET /api/v1/sku/<CODE>/price-history`
- История остатков:
  - `GET /api/v1/sku/<CODE>/inventory-history`
- Изображение SKU (fallback):
  - `GET /sku/<CODE>/image`

## Поведение листинга: infinite scroll
UI загружает страницы порциями (limit/offset) и догружает следующую страницу при прокрутке списка вниз.

Типовая диагностика:
- если отображается только первая страница (например, 30 элементов), проверьте, что:
  - «sentinel» элемент для IntersectionObserver находится внутри scroll-контейнера
  - или включён корректный fallback на scroll-событие.

## Графики
UI пытается использовать Chart.js из CDN.
Если CDN недоступен, UI должен работать без падения и показывать текстовую подсказку вместо графика.

## Как применить изменения UI
1) Обновить `api/templates/ui.html`.
2) Пересобрать и перезапустить сервис API:
   - `docker compose build api`
   - `docker compose up -d --force-recreate api`
3) Открыть: `http://localhost:18000/ui`
