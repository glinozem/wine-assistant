# Runbook: Ops Daily Import (contracts, statuses, troubleshooting)

Этот документ — **источник истины** для Ops Daily Import:
- статусы (run-level и file-level),
- контракты API,
- структура папок и правила перемещения,
- типовые проблемы и troubleshooting.

> Все запросы требуют заголовок `X-API-Key`.

---

## 1) Папки и артефакты

### 1.1 Inbox / Archive / Quarantine

- `./data/inbox/` — входящие `.xlsx` (в контейнере: `/app/data/inbox/`)
- `./data/archive/` — архивированные исходники (обычно `YYYY-MM/...`)
- `./data/quarantine/` — файлы/результаты, отправленные в карантин

### 1.2 Logs (обязательно)

- `./data/logs/daily-import/`
  - `<run_id>.json` — run log (обновляется во время RUNNING)
  - доступен для скачивания через `GET /api/v1/ops/files/logs/<relpath>`

### 1.3 Что такое “latest file” в inbox

В режиме **Auto** выбирается “самый новый файл” по `mtime` (времени последнего изменения файла).
В ответе `GET /inbox` выставляется `is_latest=true` для этого файла.

---

## 2) Статусы и семантика

### 2.1 Run-level statuses

- `RUNNING` — импорт выполняется (лог обновляется)
- `OK` — все файлы обработаны без SKIPPED/QUARANTINED/ERROR
- `OK_WITH_SKIPS` — есть `SKIPPED` и/или `QUARANTINED`, но run завершён без падения “в целом”
- `FAILED` — есть `ERROR` хотя бы по одному файлу
- `TIMEOUT` — оркестратор не дождался завершения (run оборван по таймауту)

Отдельно: ответ `POST /run` возвращает `status=STARTED` (это статус ответа API, не финальный run status).

### 2.2 File-level statuses

- `PENDING` — файл в очереди (в начальном логе, когда mode=files)
- `IMPORTED` — импорт выполнен
- `SKIPPED` — импорт пропущен (например, `skip_reason=ALREADY_IMPORTED_SAME_HASH`)
- `QUARANTINED` — файл/часть данных ушли в карантин
- `ERROR` — ошибка по файлу (например, “file not found”, timeout, ошибка ETL)

### 2.3 Поля file-level результата (фактическая модель)

Типичные поля в `files[]`:
- `original_name`
- `status`
- `skip_reason` (если SKIPPED)
- `effective_date` (если распознана)
- `envelope_id` (если получен из ETL вывода)
- `rows_good`, `rows_quarantine`
- `sha256`
- `archive_path` / `quarantine_path`
- `started_at`, `finished_at`, `duration_ms`
- `error` (если ERROR)

---

## 3) API contracts (PowerShell + curl) + примеры ответов

База: `http://localhost:18000`
Заголовок: `X-API-Key: <key>`

### 3.1 GET /api/v1/ops/daily-import/inbox

**PowerShell**
```powershell
$k = (Get-Content .\.env | ? { $_ -match '^API_KEY=' } | Select-Object -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()
irm "http://localhost:18000/api/v1/ops/daily-import/inbox" -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 5
```

**curl**
```bash
curl -sS -H "X-API-Key: $API_KEY" "http://localhost:18000/api/v1/ops/daily-import/inbox"
```

**Response (пример)**
```json
{
  "files": [
    { "name": "2025_12_25 Прайс.xlsx", "size": 123456, "mtime": "2026-01-10T12:34:56", "is_latest": true }
  ]
}
```

### 3.2 POST /api/v1/ops/daily-import/inbox/upload

Multipart form field: `files` (допускается также `files[]`).

**curl**
```bash
curl -sS -H "X-API-Key: $API_KEY" \
  -F "files=@./data/inbox/2025_12_25 Прайс.xlsx" \
  "http://localhost:18000/api/v1/ops/daily-import/inbox/upload"
```

**Response (пример)**
```json
{
  "uploaded": [
    {
      "original_name": "2025_12_25 Прайс.xlsx",
      "saved_name": "2025_12_25 Прайс.xlsx",
      "size": 123456,
      "sha256": "…",
      "status": "UPLOADED",
      "upload_id": 101
    }
  ],
  "rejected": [],
  "inbox": { "files": [ { "name": "2025_12_25 Прайс.xlsx", "is_latest": true, "size": 123456, "mtime": "…" } ] }
}
```

Типовые `rejected[].reason`:
- `DUPLICATE` (одинаковый SHA-256 уже есть в inbox)
- `ALREADY_IMPORTED_SAME_HASH` (SHA-256 уже есть в `ingest_envelope`; в ответе будет `envelope_id`)
- `INVALID_FILE`, `FILE_TOO_LARGE`, `TOTAL_TOO_LARGE`, `NAME_CONFLICT`

### 3.3 POST /api/v1/ops/daily-import/run (async)

Body:
- Auto: `{"mode":"auto"}`
- Manual list: `{"mode":"files","files":["file1.xlsx","file2.xlsx"]}`

**PowerShell**
```powershell
$body = @{ mode="auto" } | ConvertTo-Json
irm "http://localhost:18000/api/v1/ops/daily-import/run" -Method Post -Headers @{ "X-API-Key" = $k } -ContentType "application/json" -Body $body
```

**Response (пример)**
```json
{
  "run_id": "3b0b8a8a-....",
  "status": "STARTED",
  "message": "Import started. Poll GET /runs/{run_id} for status"
}
```

### 3.4 GET /api/v1/ops/daily-import/runs (history)

Query:
- `limit` (1..200, default 50)
- `cursor` (opaque)
- `status` (например `OK`, `FAILED`, `RUNNING`)
- `from`, `to` (ISO datetime)

**curl**
```bash
curl -sS -H "X-API-Key: $API_KEY" \
  "http://localhost:18000/api/v1/ops/daily-import/runs?limit=50"
```

**Response (пример)**
```json
{
  "items": [
    {
      "run_id": "…",
      "status": "OK_WITH_SKIPS",
      "requested_mode": "auto",
      "selected_mode": "AUTO_INBOX_NEWEST",
      "started_at": "…",
      "finished_at": "…",
      "duration_ms": 12345,
      "summary": { "files_total": 1, "files_imported": 0, "files_skipped": 1 }
    }
  ],
  "runs": [ /* backward-compat alias */ ],
  "next_cursor": null
}
```

### 3.5 GET /api/v1/ops/daily-import/runs/<run_id> (detail)

**PowerShell**
```powershell
$rid = "<run_id>"
irm "http://localhost:18000/api/v1/ops/daily-import/runs/$rid" -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 10
```

**Response (пример, сокращённо)**
```json
{
  "run_id": "…",
  "status": "OK",
  "requested_mode": "auto",
  "selected_mode": "AUTO_INBOX_NEWEST",
  "started_at": "…",
  "finished_at": "…",
  "duration_ms": 12345,
  "files": [
    { "original_name": "…xlsx", "status": "IMPORTED", "rows_good": 262, "rows_quarantine": 0, "archive_path": "data/archive/…" }
  ],
  "summary": { "files_total": 1, "files_imported": 1, "files_skipped": 0 }
}
```

### 3.6 GET /api/v1/ops/files/<kind>/<relpath> (download)

`kind`:
- `archive`
- `quarantine`
- `logs`

Пример (download лога):
```bash
curl -L -H "X-API-Key: $API_KEY" \
  "http://localhost:18000/api/v1/ops/files/logs/daily-import/<run_id>.json" \
  -o "<run_id>.json"
```

Ошибки:
- `400 Invalid kind`
- `403 Path traversal blocked`
- `404 File not found`

---

## 4) Troubleshooting (минимум 3 сценария)

### 4.1 “File not found …” в manual list
Причина: имя файла не совпадает с текущим inbox (файл уже перемещён в archive/quarantine прошлым run).

Что делать:
1) обновить inbox (`GET /inbox` или кнопка UI “Обновить Inbox”)
2) передавать **точное имя** из inbox

### 4.2 “NO_FILES_IN_INBOX” (Auto)
Причина: `data/inbox/` пуст.

Что делать:
- положить `.xlsx` в `./data/inbox/` (или использовать upload endpoint), затем повторить запуск.

### 4.3 403 Forbidden
Причина: отсутствует/неверный `X-API-Key`.

Что делать:
- проверьте `.env` и заголовок запроса / ввод ключа в UI.

### 4.4 PowerShell: `curl` не тот
Причина: в Windows PowerShell `curl` может быть алиасом.

Что делать:
- используйте `curl.exe` или `Invoke-RestMethod (irm)`.
