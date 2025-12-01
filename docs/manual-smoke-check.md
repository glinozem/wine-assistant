# Manual Smoke Check — Wine Assistant

Набор ручных проверок, который позволяет за 1–2 минуты понять, что стенд живой:
- контейнеры подняты;
- БД доступна;
- API отвечает;
- поиск, SKU, история и экспорт работают.

> По умолчанию примеры рассчитаны на локальный стенд:
> `http://localhost:18000`

---

## 0. Подготовка

### PowerShell

```powershell
$baseUrl = "http://localhost:18000"

# API-ключ можно взять из .env (строка API_KEY=...)
$apiKey  = "<ВСТАВЬ_СЮДА_API_KEY>"
$headers = @{ "X-API-Key" = $apiKey }
```

### curl (Linux/macOS, Git Bash)

```bash
BASE_URL="http://localhost:18000"
API_KEY="<ВСТАВЬ_СЮДА_API_KEY>"
```

---

## 1. Health / Liveness / Readiness

### 1.1. /live

**PowerShell**

```powershell
Invoke-RestMethod "$baseUrl/live"
```

Ожидаем:
- `status = "alive"`
- `version` совпадает с текущим релизом (например, `0.4.3`).

**curl**

```bash
curl "$BASE_URL/live"
```

---

### 1.2. /ready

**PowerShell**

```powershell
Invoke-RestMethod "$baseUrl/ready"
```

Ожидаем:
- `status = "ready"`
- в `checks.database` нет ошибок.

---

### 1.3. /health

**PowerShell**

```powershell
Invoke-RestMethod "$baseUrl/health"
```

Ожидаем:
- ответ `ok` / `True` (в зависимости от формата).

---

## 2. Базовый поиск по каталогу

### 2.1. Поиск 3 товаров

**PowerShell**

```powershell
$search = Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=3" -Headers $headers
$search.items | Select-Object code, name, price_final_rub | Format-Table
```

Ожидаем:
- `items` не пустой;
- у каждого товара есть `code`, `name`, `price_final_rub`;
- поля enrichment: `producer_site`, `image_url`, `winery_name_ru`, `winery_description_ru` присутствуют в объекте.

**curl (только посмотреть «сырое» тело)**

```bash
curl -H "X-API-Key: $API_KEY"   "$BASE_URL/api/v1/products/search?limit=3"
```

---

## 3. SKU API + history

### 3.1. Карточка SKU

Выбираем любой код из поиска:

```powershell
$code = $search.items[0].code
$code
```

Запрашиваем SKU:

```powershell
$sku = Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers
$sku
```

Ожидаем:
- те же поля, что в поиске;
- дополнительно: `supplier_ru`, `title_ru`, `winery_description_ru` и т.п.

---

### 3.2. История цен

```powershell
$priceHistory = Invoke-RestMethod `
  "$baseUrl/api/v1/sku/$code/price-history?from=2025-01-01&to=2025-12-31&limit=50" `
  -Headers $headers

$priceHistory
```

Ожидаем:
- `code` совпадает с `$code`;
- `items` — список записей с `effective_from`, `effective_to`, `price_rub`.

---

### 3.3. История остатков

```powershell
$invHistory = Invoke-RestMethod `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31&limit=50" `
  -Headers $headers

$invHistory
```

Ожидаем:
- запрос не падает с ошибкой;
- `code` совпадает с `$code`;
- `items` либо пустой объект, либо список записей (в зависимости от наличия данных).

---

## 4. Экспорт (JSON-режим)

Чтобы не создавать файлы, для smoke-теста используем формат `json`.

### 4.1. Экспорт поиска

```powershell
$exportSearch = Invoke-RestMethod `
  "$baseUrl/api/v1/export/search?format=json&limit=3" `
  -Headers $headers

$exportSearch | Select-Object -First 1
```

Ожидаем:
- структура аналогична поиску, но в «экспортном» формате;
- нет ошибок и статус HTTP 200.

---

### 4.2. Экспорт SKU

```powershell
$exportSku = Invoke-RestMethod `
  "$baseUrl/api/v1/export/sku/$code?format=json" `
  -Headers $headers

$exportSku
```

Ожидаем:
- та же информация, что и в `/api/v1/sku/$code`;
- пригодно для генерации PDF-карточки.

---

### 4.3. Экспорт истории цен

```powershell
$exportPriceHistory = Invoke-RestMethod `
  "$baseUrl/api/v1/export/price-history/$code?format=json" `
  -Headers $headers

$exportPriceHistory
```

Ожидаем:
- структура как у эндпоинта `/price-history`, но в экспортном формате;
- запрос отрабатывает без ошибок.

---

## 5. Критерии успешного smoke-теста

Smoke-тест считаем **успешным**, если:

1. `/live`, `/ready`, `/health` возвращают ожидаемые статусы.
2. Поиск по каталогу (`/products/search`) выдаёт хотя бы один товар.
3. SKU-эндпоинт и история цен/остатков по выбранному SKU работают.
4. Все экспортные эндпоинты (`/export/...`) отвечают с HTTP 200 и валидным JSON.
5. Нигде не получаем HTTP 5xx или неожиданные исключения.

Если какой-то шаг падает, фиксируем:
- какой именно запрос;
- HTTP-статус и текст ошибки;
и заводим Issue в репозитории.
