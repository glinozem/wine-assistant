# Runbook: Ops Daily Import (inbox → archive/quarantine)

Этот runbook описывает **текущий** поток импорта прайс‑листов через Ops Daily Import:
- вход: `data/inbox/*.xlsx`
- выход: `data/archive/YYYY-MM/...` (и/или `data/quarantine/...` при проблемах)

Импорт идемпотентный: если файл уже был импортирован ранее (тот же SHA‑256), он будет помечен `SKIPPED` с причиной `ALREADY_IMPORTED_SAME_HASH` и, как правило, перемещён в archive.

---

## 0) Предварительные условия

1. Запущены сервисы:

```powershell
docker-compose up -d --build db api
```

2. Есть API key (в `.env`):

```env
API_KEY=...
```

3. В `data/inbox/` лежит один или несколько `.xlsx` файлов.

Проверка с хоста и из контейнера:

```powershell
Get-ChildItem .\data\inbox

docker-compose exec api ls -la /app/data/inbox
```

---

## 1) Быстрый старт (Windows)

### Вариант A: Web UI

1. Откройте `http://localhost:18000/daily-import`
2. Введите `X-API-Key`
3. Нажмите **«Обновить Inbox»**
4. Запустите импорт в режиме **Auto** или **Manual (selected files)**

### Вариант B: PowerShell wrapper

```powershell
# Auto: обработать самый новый файл
.\scripts\run_daily_import.ps1 -Mode auto

# Manual list (имена должны совпадать с inbox)
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"
```

---

## 2) Makefile команды

```powershell
# inbox
make inbox-ls

# auto
make daily-import

# manual list (простые имена)
make daily-import-files FILES="file1.xlsx file2.xlsx"

# manual list (Windows-friendly, пробелы/кириллица)
make daily-import-files-ps FILES="2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"

# просмотр истории и run по id
make daily-import-history
make daily-import-show RUN_ID=<uuid>
```

---

## 3) Проверка результата и интерпретация статусов

### 3.1 Получить список inbox по API

```powershell
$k = (Get-Content .\.env | Where-Object { $_ -match '^API_KEY=' } | Select-Object -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()

irm "http://localhost:18000/api/v1/ops/daily-import/inbox" `
  -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 5
```

### 3.2 Посмотреть детали run

```powershell
$rid = "<run_id>"
irm "http://localhost:18000/api/v1/ops/daily-import/runs/$rid" `
  -Headers @{ "X-API-Key" = $k } | ConvertTo-Json -Depth 10
```

### 3.3 Статусы

**Run status** (верхний уровень):
- `OK` — все файлы обработаны успешно
- `OK_WITH_SKIPS` — есть `SKIPPED` файлы, но ошибок нет
- `FAILED` — есть `ERROR`/падение обработки хотя бы одного файла
- `TIMEOUT` — оркестратор не дождался завершения

**File status** (по каждому файлу):
- `IMPORTED` — импорт выполнен
- `SKIPPED` — импорт не нужен (часто `ALREADY_IMPORTED_SAME_HASH`)
- `QUARANTINED` — файл/часть данных попали в карантин
- `ERROR` — ошибка по файлу (например, файл не найден в inbox)

---

## 4) Частые проблемы

### 4.1 “File not found …”

Причина: в manual list передано имя файла, которого нет в `data/inbox/` (часто — **устаревший выбор**: файл уже был перемещён в archive прошлым запуском).

Что делать:
1. Нажать **«Обновить Inbox»** в UI или выполнить `make inbox-ls`
2. Запускать импорт, передавая **точное имя** из inbox

### 4.2 “NO_FILES_IN_INBOX” (Auto)

Причина: `data/inbox/` пуст.

Что делать: добавить `.xlsx` в `data/inbox/`, затем повторить запуск.

### 4.3 “Forbidden / 403”

Причина: отсутствует или неверный `X-API-Key`.

Что делать: убедиться, что API key берётся из `.env` и передаётся в запросе / введён в UI.

---

## 5) Housekeeping

### 5.1 Очистка архива

```powershell
make daily-import-cleanup-archive DAYS=90
```

### 5.2 Статистика по quarantine

```powershell
make daily-import-quarantine-stats
```
