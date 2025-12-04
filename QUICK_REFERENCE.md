# Wine Assistant - Краткая шпаргалка по новым возможностям

## 🔑 Базовая настройка PowerShell

```powershell
# Установка API ключа
$env:API_KEY = "ВАШ_API_КЛЮЧ"

# Базовые переменные
$baseUrl = "http://localhost:18000"
$headers = @{ "X-API-Key" = $env:API_KEY }

# Проверка
echo $env:API_KEY
```

---

## 🧪 Smoke Check (Проверка работоспособности)

### Быстрая проверка

```powershell
# Запуск quick smoke check
.\scripts\quick_smoke_check.ps1

# Результат: проверка health, search, основных эндпоинтов
```

### Полная проверка

```powershell
# Запуск полного smoke check
.\scripts\manual_smoke_check.ps1

# Результат:
# - Health endpoints (✅)
# - Search API (✅)
# - SKU details (✅)
# - Price history (✅)
# - Inventory history (✅)
# - Export endpoints (✅)
```

---

## 📊 Синхронизация истории остатков

### Ручной запуск

```powershell
# Через Python
python scripts/sync_inventory_history.py

# Через Docker
docker compose exec api python scripts/sync_inventory_history.py

# Dry-run (без изменений в БД)
python scripts/sync_inventory_history.py --dry-run

# На конкретную дату
python scripts/sync_inventory_history.py --as-of 2025-12-05T00:00:00
```

### Через Makefile

```powershell
# Dry-run режим
make sync-inventory-history-dry-run

# Реальная синхронизация
make sync-inventory-history
```

### Автоматическая синхронизация (Windows)

**Task Scheduler настройка:**

1. Открыть **Task Scheduler**
2. Create Task → Name: "Wine Assistant Inventory Sync"
3. **Triggers:** Daily at 03:00 AM
4. **Actions:**
   - Program: `powershell.exe`
   - Arguments:
     ```
     -NoProfile -ExecutionPolicy Bypass -Command "cd 'D:\path\to\wine-assistant'; make sync-inventory-history"
     ```
5. Run → Test

---

## 📈 API: История остатков

### Получить историю через API

```powershell
# История остатков по SKU
$code = "D010210"
Invoke-RestMethod "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31&limit=50" -Headers $headers

# Через curl + jq (красивый вывод)
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31&limit=10" | jq
```

### Фильтрация данных (jq)

```powershell
# Только нужные поля
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2025-01-01&to=2025-12-31" | `
  jq '.items[] | {as_of, stock_total, stock_free, reserved}'

# Проверка типов (должны быть "number")
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/api/v1/sku/$code/inventory-history?limit=1" | `
  jq '.items[0] | {
    stock_total_type: (.stock_total | type),
    stock_free_type: (.stock_free | type)
  }'
```

---

## 📤 Экспорт истории остатков

### JSON

```powershell
# Экспорт в JSON
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$baseUrl/export/inventory-history/$code?format=json&limit=100" | `
  jq > "inventory_$code.json"
```

### Excel

```powershell
# Экспорт в XLSX
$code = "D010210"
$url = "$baseUrl/export/inventory-history/${code}?format=xlsx&limit=200"
Invoke-WebRequest $url -Headers $headers -OutFile "inventory_$code.xlsx"

# Альтернатива через curl
curl.exe -H "X-API-Key: $env:API_KEY" `
  "$url" `
  -o "inventory_$code.xlsx"
```

---

## 📊 Проверка данных в БД

### Через Docker psql

```powershell
# Последние 20 снимков
docker compose exec db psql -U postgres -d wine_db -c `
  "SELECT code, stock_total, stock_free, as_of FROM inventory_history ORDER BY as_of DESC LIMIT 20;"

# История конкретного SKU
docker compose exec db psql -U postgres -d wine_db -c `
  "SELECT code, stock_total, stock_free, as_of FROM inventory_history WHERE code='D010210' ORDER BY as_of DESC;"
```

### Через Adminer

1. Открыть http://localhost:18080
2. Login: postgres / postgres
3. Database: wine_db
4. SQL запрос:

```sql
SELECT code, stock_total, stock_free, reserved, as_of
FROM inventory_history
WHERE code = 'D010210'
ORDER BY as_of DESC
LIMIT 50;
```

---

## 📈 График: История цен

### API запрос

```powershell
# Получить данные для графика
$code = "D010210"
$priceData = Invoke-RestMethod `
  "$baseUrl/api/v1/sku/$code/price-history?from=2020-01-01&to=2030-12-31&limit=100" `
  -Headers $headers

# Посмотреть структуру
$priceData.items | Format-Table effective_from, effective_to, price_rub
```

### JavaScript для Chart.js

```javascript
const response = await fetch(
  `/api/v1/sku/${code}/price-history?from=2020-01-01&to=2030-12-31`,
  { headers: { 'X-API-Key': API_KEY } }
);
const data = await response.json();

const ctx = document.getElementById('priceChart').getContext('2d');
new Chart(ctx, {
  type: 'line',
  data: {
    labels: data.items.map(p => p.effective_from),
    datasets: [{
      label: 'Цена, ₽',
      data: data.items.map(p => p.price_rub),
      borderColor: 'rgba(75, 192, 192, 1)',
      backgroundColor: 'rgba(75, 192, 192, 0.15)'
    }]
  }
});
```

---

## 📈 График: История остатков

### API запрос

```powershell
# Получить данные для графика
$inventoryData = Invoke-RestMethod `
  "$baseUrl/api/v1/sku/$code/inventory-history?from=2020-01-01&to=2030-12-31&limit=100" `
  -Headers $headers

# Посмотреть структуру
$inventoryData.items | Format-Table as_of, stock_total, stock_free, reserved
```

### JavaScript для Chart.js

```javascript
const response = await fetch(
  `/api/v1/sku/${code}/inventory-history?from=2020-01-01&to=2030-12-31`,
  { headers: { 'X-API-Key': API_KEY } }
);
const data = await response.json();

const ctx = document.getElementById('inventoryChart').getContext('2d');
new Chart(ctx, {
  type: 'line',
  data: {
    labels: data.items.map(p => p.as_of),
    datasets: [
      {
        label: 'Общий остаток',
        data: data.items.map(p => p.stock_total),
        borderColor: 'rgba(54, 162, 235, 1)'
      },
      {
        label: 'Свободный',
        data: data.items.map(p => p.stock_free),
        borderColor: 'rgba(75, 192, 192, 1)',
        borderDash: [4, 4]
      }
    ]
  }
});
```

---

## 🔍 Полезные jq фильтры

### Базовая фильтрация

```powershell
# Только определённые поля
... | jq '.items[] | {code, stock_total, as_of}'

# Первый элемент
... | jq '.items[0]'

# Последние N элементов
... | jq '.items[-5:]'

# Количество элементов
... | jq '.items | length'
```

### Проверка типов

```powershell
# Типы всех полей первого элемента
... | jq '.items[0] | to_entries | map({key, type: (.value | type)})'

# Конкретное поле
... | jq '.items[0].stock_total | type'
```

### Агрегация

```powershell
# Сумма всех остатков
... | jq '[.items[].stock_total] | add'

# Средний остаток
... | jq '[.items[].stock_total] | add / length'

# Максимальный остаток
... | jq '[.items[].stock_total] | max'

# Минимальный остаток
... | jq '[.items[].stock_total] | min'
```

---

## 🐳 Docker команды

### Управление контейнерами

```powershell
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск одного сервиса
docker compose restart api

# Логи
docker compose logs api -f

# Статус
docker compose ps
```

### Выполнение команд в контейнере

```powershell
# Синхронизация остатков
docker compose exec api python scripts/sync_inventory_history.py

# Загрузка прайса
docker compose exec api python scripts/load_csv.py --excel /data/inbox/price.xlsx

# Проверка миграций
docker compose exec db psql -U postgres -d wine_db -c "SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"
```

---

## 📝 Быстрые проверки

### Health Check

```powershell
# Liveness
Invoke-RestMethod "$baseUrl/live"

# Readiness
Invoke-RestMethod "$baseUrl/ready"

# Health
Invoke-RestMethod "$baseUrl/health"
```

### Поиск товаров

```powershell
# Простой поиск
Invoke-RestMethod "$baseUrl/api/v1/products/search?limit=5" -Headers $headers

# С фильтрами
Invoke-RestMethod "$baseUrl/api/v1/products/search?color=red&in_stock=true&limit=10" -Headers $headers
```

### Карточка SKU

```powershell
# Полная карточка
$code = "D010210"
Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers | ConvertTo-Json -Depth 10

# Только цены и остатки
Invoke-RestMethod "$baseUrl/api/v1/sku/$code" -Headers $headers |
  Select-Object code, price_list_rub, price_final_rub, stock_total, stock_free
```

---

## 🛠️ Troubleshooting

### Проблема: API ключ не работает

```powershell
# Проверить переменную
echo $env:API_KEY

# Переустановить
$env:API_KEY = "новый_ключ"

# Проверить в .env файле
cat .env | Select-String "API_KEY"
```

### Проблема: Контейнер не стартует

```powershell
# Посмотреть логи
docker compose logs api --tail=50

# Проверить статус
docker compose ps

# Пересоздать контейнер
docker compose up -d --force-recreate api
```

### Проблема: Данные не синхронизируются

```powershell
# Проверить dry-run
python scripts/sync_inventory_history.py --dry-run

# Проверить логи
python scripts/sync_inventory_history.py 2>&1 | Tee-Object -FilePath sync.log

# Проверить права доступа к БД
docker compose exec db psql -U postgres -d wine_db -c "SELECT current_user, current_database();"
```

---

## 📚 Полезные ссылки

- **Swagger UI:** http://localhost:18000/docs
- **Adminer:** http://localhost:18080
- **GitHub Issues:** https://github.com/glinozem/wine-assistant/issues
- **README:** [README.md](README.md)
- **Manual Smoke Check:** [docs/manual-smoke-check.md](docs/manual-smoke-check.md)

---

**Создано:** 04 декабря 2025
**Версия:** 1.0
**Для:** Wine Assistant v0.5.0
