# Как дергать `/run-sync` из PowerShell (Windows PowerShell 5.1 vs PowerShell 7+)

> Endpoint: `POST /api/v1/ops/daily-import/run-sync` (sync, **debug-only**).
> Для обычной эксплуатации используйте `POST /api/v1/ops/daily-import/run` (async) или `scripts/run_daily_import.ps1`.

## TL;DR

- **Самый надёжный способ (5.1 и 7+):** `Invoke-RestMethod`.
- **Если нужен именно `curl.exe`:** передавайте body через **stdin** (`--data-binary '@-'`), тогда PowerShell не “ломает” кавычки.

---

## 0) Подготовка переменных (base URL, API key, body)

```powershell
# База (docker compose по умолчанию: 127.0.0.1:18000 -> 8000)
$base = "http://localhost:18000"
$url  = "$base/api/v1/ops/daily-import/run-sync"

# API key из .env (trim + снять кавычки)
$apiKeyLine = (Get-Content .env | Where-Object { $_ -match '^\s*API_KEY\s*=' } | Select-Object -First 1)
$apiKey     = ($apiKeyLine -replace '^\s*API_KEY\s*=\s*','').Trim().Trim('"')

# Payload (auto / files)
$body = @{ mode = "auto"; files = @() } | ConvertTo-Json -Compress
```

---

## 1) Рекомендуется: `Invoke-RestMethod` (PowerShell 5.1 и 7+)

### mode=auto
```powershell
Invoke-RestMethod -Method Post -Uri $url `
  -Headers @{ "X-API-Key" = $apiKey } `
  -ContentType "application/json" `
  -Body $body
```

### mode=files (файлы должны быть в `data/inbox/`)
```powershell
$bodyFiles = @{ mode = "files"; files = @("2025_12_24 Прайс.xlsx") } | ConvertTo-Json -Compress

Invoke-RestMethod -Method Post -Uri $url `
  -Headers @{ "X-API-Key" = $apiKey } `
  -ContentType "application/json" `
  -Body $bodyFiles
```

---

## 2) `curl.exe`: универсально и без сюрпризов (stdin + `--data-binary '@-'`)

⚠️ В Windows PowerShell 5.1 (а иногда и в 7+) при **inline** body PowerShell может “съесть” двойные кавычки, и сервер увидит не-JSON вида `{mode:auto,files:[]}` → `{"error":"Invalid JSON"}`.

Решение: **передать JSON через stdin**:

```powershell
# Важно: использовать именно curl.exe (а не алиас curl)
$body | & "$env:SystemRoot\System32\curl.exe" -sS -i -X POST $url `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $apiKey" `
  --data-binary '@-'
```

---

## 3) `curl.exe`: без stdin (workaround через экранирование кавычек)

Если очень нужно передать body “как аргументом” (не через stdin), то:
- сформируйте JSON строкой,
- **экранируйте** двойные кавычки `"`.

```powershell
$bodyEsc = $body.Replace('"','\"')

& "$env:SystemRoot\System32\curl.exe" -sS -i -X POST $url `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $apiKey" `
  --data-raw $bodyEsc
```

---

## 4) Почему `--data-raw '{"mode":"auto","files":[]}'` иногда ломается

Симптом: вы пишете корректный JSON, но сервер отвечает `Invalid JSON`, а в диагностике видно, что пришло `{mode:auto,files:[]}`.

Причина: PowerShell может по-своему интерпретировать кавычки/скобки при передаче аргументов в native process (curl.exe). На практике это чаще всего проявляется в Windows PowerShell 5.1.

✅ “Железобетонные” варианты: `Invoke-RestMethod` или `curl.exe` через stdin (`--data-binary '@-'`).

---

## 5) PowerShell 7+: заметки про argument passing

Если вы на PowerShell 7+ и всё равно видите, что `curl.exe --data-raw $body` “теряет” кавычки:

1) Проверьте, какие правила передачи аргументов активны:
```powershell
$PSVersionTable.PSVersion
$PSNativeCommandArgumentPassing   # может отсутствовать в старых версиях 7.x
```

2) Не тратьте время на тонкую настройку — используйте **stdin** вариант из раздела 2.

---

## 6) Быстрая диагностика: что реально ушло в curl

```powershell
$trace = Join-Path $PWD "curl-trace.txt"

& "$env:SystemRoot\System32\curl.exe" -v --trace-ascii $trace -X POST $url `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $apiKey" `
  --data-raw $body

Get-Content $trace -Tail 80
```

Ожидаемо в trace должно быть что-то вроде:
- `Content-Length: ...`
- тело запроса с кавычками: `{"files":[],"mode":"auto"}`

---

## 7) (Опционально) Диагностика на сервере: `received_body_tail`

Endpoint `/run-sync` умеет включать поле `received_body_tail` в ответе 400 (для ускорения отладки), если выставить env:

- для локального запуска: `OPS_DB_REGISTRY_DEBUG=1` (в окружении API контейнера).

> Не включайте это в production: это диагностический режим.
