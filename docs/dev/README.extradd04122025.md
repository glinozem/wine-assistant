# Дополнительная документация: PowerShell, smoke-check и inventory-history

## 🔑 1. Установка переменной окружения API_KEY в PowerShell

``` powershell
$env:API_KEY = "ВАШ_API_КЛЮЧ"
echo $env:API_KEY
```

## 🚀 2. Запуск quick_smoke_check.ps1

``` powershell
.\scripts\quick_smoke_check.ps1
```

## 🧪 3. Полный smoke-check: manual_smoke_check.ps1

``` powershell
.\scripts\manual_smoke_check.ps1
```

## 📂 4. Как правильно собирать URL в PowerShell

### Вариант 1 --- интерполяция `${}`

``` powershell
$url = "$baseUrl/export/sku/${code}?format=json"
Invoke-RestMethod $url -Headers $headers
```

### Вариант 2 --- форматирование (-f)

``` powershell
$url = "{0}/export/sku/{1}?format=json" -f $baseUrl, $code
Invoke-RestMethod $url -Headers $headers
```

## 📄 5. Загрузка прайсов в хронологическом порядке

``` powershell
$priceFiles = Get-ChildItem -Path $InboxDir "*.xlsx" | Sort-Object {
    Get-DateFromFilename $_.Name
}
```

## 📦 6. Синхронизация остатков

### Обычный режим

``` powershell
docker compose exec api python scripts/sync_inventory_history.py
```

### Dry‑run

``` powershell
docker compose exec api python scripts/sync_inventory_history.py --dry-run
```

### На определённую дату

``` powershell
docker compose exec api `
  python scripts/sync_inventory_history.py `
  --as-of 2025-12-05T00:00:00
```

## 📊 7. Пример результата экспорта остатков

  Дата as_of   Остаток   Резерв   Свободно
  ------------ --------- -------- ----------
  2025‑12‑04   11371     0        11263
  2025‑12‑05   11371     0        11263
