# Windows / PowerShell: запросы к API (curl, Invoke-RestMethod)

## Почему `curl -H ...` иногда не работает
В PowerShell команда `curl` часто является алиасом `Invoke-WebRequest`.
В результате синтаксис `-H "Header: Value"` работает не так, как в bash.

## Рекомендуемые варианты

### Вариант 1 — curl.exe (нативный curl)
```powershell
curl.exe -s "http://localhost:18000/health" -H "X-API-Key: $env:API_KEY"
curl.exe -s "http://localhost:18000/api/v1/products/search?limit=30&offset=0&in_stock=true" `
  -H "X-API-Key: $env:API_KEY"
```

### Вариант 2 — Invoke-RestMethod
```powershell
Invoke-RestMethod "http://localhost:18000/api/v1/products/search?limit=30&offset=30&in_stock=true" `
  -Headers @{ "X-API-Key" = $env:API_KEY }
```

## Быстрые подсказки
- Если нужен только статус/заголовки: `curl.exe -i ...`
- Если нужно сохранить вывод в файл: `| Out-File -Encoding utf8 out.json`
