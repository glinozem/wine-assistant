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

```powershell
Invoke-RestMethod "$baseUrl/live"
```

### 1.2. /ready

```powershell
Invoke-RestMethod "$baseUrl/ready"
```

### 1.3. /health

```powershell
Invoke-RestMethod "$baseUrl/health"
```

---

## 2. Базовый поиск по каталогу

```powershell
$search = Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=3" -Headers $headers
$search.items | Select-Object code, name, price_final_rub | Format-Table
```

---

## 3. SKU API + history

### 3.1. Получение SKU

```powershell
$code = $search.items[0].code
Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers
```

### 3.2. История цен

```powershell
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/price-history?from=2025-01-01&to=2025-12-31&limit=50" -Headers $headers
```

### 3.3. История остатков

```powershell
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31&limit=50" -Headers $headers
```

---

## 4. Экспорт (JSON-режим)

### 4.1. Экспорт поиска

```powershell
Invoke-RestMethod "$baseUrl/api/v1/export/search?format=json&limit=3" -Headers $headers
```

### 4.2. Экспорт SKU

```powershell
Invoke-RestMethod "$baseUrl/api/v1/export/sku/$code?format=json" -Headers $headers
```

### 4.3. Экспорт истории цен

```powershell
Invoke-RestMethod "$baseUrl/api/v1/export/price-history/$code?format=json" -Headers $headers
```

---

## 5. Критерии успешного smoke-теста

1. `/live`, `/ready`, `/health` возвращают ожидаемые статусы.
2. Поиск (`/products/search`) возвращает не пустой список.
3. SKU и history работают без ошибок.
4. Экспортные эндпоинты возвращают корректный JSON.
5. Нет HTTP 5xx и неожиданных исключений.

---

## 6. Быстрый чек-лист на будущее (URL и PowerShell)

Когда что-то странное на уровне URL (например, `/sku/=json`):

### 1. Всегда печатай URL перед запросом

```powershell
$exportUrl = "$baseUrl/api/v1/export/sku/$code?format=json"
$exportUrl
```

### 2. Если видишь «пустой» SKU в URL

```powershell
"sku = [$code]"
```

Если там пусто — переприсвой переменную вручную.

### 3. Для строк с параметрами в PowerShell всегда безопасно писать так:

```powershell
"$baseUrl/api/v1/export/sku/$($code)?format=json"
```

Использование `$($code)` исключает неочевидное поведение интерполяции.

---
