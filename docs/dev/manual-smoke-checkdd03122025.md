# Ручной смоук-чек Wine Assistant (manual smoke check)

Этот документ описывает, как вручную проверить, что стенд Wine Assistant
(backend API + БД + миграции) поднят корректно и основные эндпоинты работают
как ожидается.

Документ ориентирован на **Windows + PowerShell** и использует:

- `docker compose` — для управления стендом,
- `curl.exe` — для HTTP-запросов,
- `jq` — для удобного просмотра JSON-ответов,
- скрипт `scripts/manual_smoke_check.ps1` — для автоматизации проверки.

---

## 1. Предварительные требования

1. Установлен **Docker Desktop** (Windows 11).
2. Клонирован репозиторий `wine-assistant`.
3. В корне проекта настроен `.env` (можно на базе `.env.example`).
4. В системе установлен `jq` (см. ниже).

### 1.1. Установка `jq` на Windows

Проще всего — через Chocolatey:

```powershell
choco install jq -y
```

После установки команда `jq` должна быть доступна в PowerShell.

Проверка:

```powershell
jq --version
```

---

## 2. Подъём стенда через Docker Compose

В PowerShell из корня проекта:

```powershell
cd D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine-assistant

docker compose build
docker compose up -d
```

Проверка статуса контейнеров:

```powershell
docker compose ps
```

Ожидаемый результат (пример):
```text
NAME                     IMAGE                       COMMAND                  SERVICE   STATUS                    PORTS
wine-assistant-adminer   adminer:4                   "entrypoint.sh docke…"   adminer   Up                        127.0.0.1:18080->8080/tcp
wine-assistant-api       wine-assistant-api:latest   "sh -lc 'gunicorn --…"   api       Up (healthy)             127.0.0.1:18000->8000/tcp
wine-assistant-db        pgvector/pgvector:pg16      "docker-entrypoint.s…"   db        Up (healthy)             127.0.0.1:15432->5432/tcp
wine-assistant-migrator  wine-assistant-api:latest   "sh -lc 'python scri…"   migrator  Exited (0)
```

Важно:

- `db` и `api` должны быть **healthy**;
- `migrator` должен корректно завершиться (Exited (0)).

---

## 3. Базовые health-checks

Базовый URL API:

```powershell
$baseUrl = "http://localhost:18000"
```

### 3.1. Liveness (`/live`)

```powershell
Invoke-RestMethod "$baseUrl/live"
```

Ожидается JSON вида:

```jsonc
{
  "started_at": "2025-12-03T05:13:03.226951+00:00",
  "status": "alive",
  "timestamp": "2025-12-03T05:13:37.901021+00:00",
  "uptime_seconds": 34.67407,
  "version": "0.4.0"
}
```

### 3.2. Readiness (`/ready`)

```powershell
Invoke-RestMethod "$baseUrl/ready"
```

Пример ответа:

```jsonc
{
  "checks": { "database": {} },
  "response_time_ms": 42.4,
  "status": "ready",
  "timestamp": "2025-12-03T05:13:38.464068+00:00",
  "version": "0.4.0"
}
```

### 3.3. `/health`

```powershell
Invoke-RestMethod "$baseUrl/health"
```

Ожидается текстовый ответ:

```text
True
```

или JSON:

```bash
curl.exe http://localhost:18000/health
# {"ok":true}
```

---

## 4. API-ключ и переменные окружения в PowerShell

Для защищённых эндпоинтов нужен заголовок `X-API-Key`.

Если в `.env` есть строка `API_KEY=...`, можно либо:

- задать переменную окружения PowerShell:

  ```powershell
  $env:API_KEY = "ВАШ_API_КЛЮЧ"
  ```

- либо явно указать ключ:

  ```powershell
  $apiKey  = "ВАШ_API_КЛЮЧ"
  $headers = @{ "X-API-Key" = $apiKey }
  ```

Далее в примерах будем использовать `$env:API_KEY` и `$baseUrl`.

---

## 5. Ручные проверки через curl.exe + jq

Этот раздел полезен, если нужно быстро глазами убедиться, что данные и типы
в ответах корректные.

### 5.1. Карточка SKU (`/api/v1/sku/<code>`)

```powershell
$code = "D010210"

curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code" |
  jq
```

Сокращённый вывод ключевых полей:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code" |
  jq '{
    code,
    name,
    country,
    region,
    price_list_rub,
    price_final_rub,
    stock_total,
    stock_free,
    vivino_rating
  }'
```

Проверка типов (важно, что цены и остатки — числа, а не строки):

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code" |
  jq '{
    code,
    price_list_rub,
    price_final_rub,
    stock_total,
    stock_free,
    price_list_rub_type: ( .price_list_rub | type ),
    price_final_rub_type: ( .price_final_rub | type ),
    stock_total_type: ( .stock_total | type ),
    stock_free_type: ( .stock_free | type )
  }'
```

Ожидается, что типы будут `"number"`.

---

### 5.2. Поиск по каталогу (`/api/v1/products/search`)

Пример простого запроса:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/products/search?limit=3&in_stock=true" |
  jq '.items[] | {
    code,
    price_list_rub,
    price_final_rub,
    stock_total,
    stock_free
  }'
```

Проверка типов в первом элементе списка:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/products/search?limit=1&in_stock=true" |
  jq '.items[0] | {
    price_list_rub_type: ( .price_list_rub | type ),
    price_final_rub_type: ( .price_final_rub | type ),
    stock_total_type: ( .stock_total | type ),
    stock_free_type: ( .stock_free | type )
  }'
```

---

### 5.3. История цен (API vs экспорт)

#### 5.3.1. API: `/api/v1/sku/<code>/price-history`

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/D010210/price-history?from=2020-01-01&to=2030-12-31&limit=10" |
  jq '.items[] | {effective_from, effective_to, price_rub}'
```

Тип `price_rub` можно проверить так:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/D010210/price-history?from=2020-01-01&to=2030-12-31&limit=1" |
  jq '.items[0].price_rub | type'
# "number"
```

#### 5.3.2. Экспорт: `/export/price-history/<code>?format=json`

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/price-history/D010210?format=json&limit=10" |
  jq '.items[] | {
    effective_from,
    effective_to,
    price_list_rub,
    price_final_rub
  }'
```

Важно:

- В **экспортном** JSON нет поля `price_rub`, только `price_list_rub` и `price_final_rub`.
- Если написать в `jq` поле, которого нет, например:

  ```powershell
  ... | jq '.items[] | {effective_from, effective_to, price_rub}'
  ```

  то `price_rub` будет `null` — это нормальное поведение `jq` (а не ошибка API).

Если нужен алиас `price_rub` в `jq`:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/price-history/D010210?format=json&limit=10" |
  jq '.items[] | {
    effective_from,
    effective_to,
    price_rub: .price_final_rub
  }'
```

---

### 5.4. История остатков (API и экспорт)

#### 5.4.1. API: `/api/v1/sku/<code>/inventory-history`

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/D010210/inventory-history?from=2020-01-01&to=2030-12-31&limit=10" |
  jq '.items[] | {as_of, stock_total, stock_free, reserved}'
```

Проверка типов:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/D010210/inventory-history?from=2020-01-01&to=2030-12-31&limit=1" |
  jq '.items[0] | {
    stock_total_type: ( .stock_total | type ),
    stock_free_type: ( .stock_free | type ),
    reserved_type: ( .reserved | type )
  }'
# Все три должны быть "number"
```

#### 5.4.2. Экспорт: `/export/inventory-history/<code>`

JSON:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/inventory-history/D010210?format=json&limit=5" |
  jq
```

Пример ответа:

```jsonc
{
  "code": "D010210",
  "items": [
    {
      "as_of": "2025-12-02 15:26:28.671832",
      "reserved": 0,
      "stock_free": 12334,
      "stock_total": 12502
    }
  ],
  "limit": 5,
  "offset": 0,
  "total": 1
}
```

XLSX:

```powershell
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/inventory-history/D010210?format=xlsx&limit=20" `
  -o inventory_history_D010210.xlsx
```

---

## 6. Скрипт `scripts/manual_smoke_check.ps1`

Для автоматизации вышеописанных шагов используется скрипт:

```text
scripts/manual_smoke_check.ps1
```

Он выполняет:

1. Проверку `/live`, `/ready`, `/health`.
2. Вызов `/api/v1/products/search?limit=3` и выбор одного SKU.
3. Проверку:
   - `/api/v1/sku/<code>`
   - `/api/v1/sku/<code>/price-history`
   - `/api/v1/sku/<code>/inventory-history`
4. Проверку экспортных эндпоинтов:
   - `/export/search?format=json&limit=3`
   - `/export/sku/<code>?format=json`
   - `/export/price-history/<code>?format=json`
   - `/export/inventory-history/<code>?format=json&limit=3`

Запуск из корня проекта:

```powershell
.\scripts\manual_smoke_check.ps1
```

В конце скрипт выводит таблицу с результатами (Name / Success / Optional / Status / Message).
Если какой-то критичный чек не проходит, скрипт завершится с ошибкой.

---

## 7. Рекомендованный порядок ручной проверки

1. `docker compose up -d` — поднять стенд.
2. Проверить `/live`, `/ready`, `/health` (вручную или через скрипт).
3. Выполнить `.\scripts\manual_smoke_check.ps1`.
4. При необходимости — использовать блоки из раздела 5 для детального анализа
   конкретных SKU, истории цен или остатков.
