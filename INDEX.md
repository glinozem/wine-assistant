# Wine Assistant — INDEX

Актуальная навигация по документации и ключевым точкам проекта.
Обновлено: 2025-12-22.

## Документы

- **README.md** — обзор проекта, архитектура, запуск (Docker Compose), основные эндпойнты API и примеры запросов.
- **QUICK_REFERENCE.md** — «шпаргалка» по самым частым командам и сценариям: запуск/проверка, быстрый smoke-check, типовые запросы к API, диагностика, **observability команды**.
- **CHANGELOG.md** — история изменений по релизам/итерациям.
- **project-structure.txt** — структура репозитория (файлы/папки как в рабочей директории и tracked в Git).

## Что изменилось в проекте (важное для разработчика)

### Observability & Monitoring (NEW — 2025-12-22)

- **Grafana Dashboard** для мониторинга backup/DR операций:
  - URL: `http://localhost:15000/d/wine-assistant-backup-dr/backup-dr`
  - Панели: Backups completed, Age since last backup, Restore operations, Remote pruned backups
  - Auto-refresh каждые 30 секунд
- **Structured JSONL logging** для backup/DR операций:
  - Логи: `logs/backup-dr/events.jsonl`
  - 10+ типов событий с метаданными (file size, duration, counts)
- **Promtail → Loki → Grafana pipeline**:
  - Promtail скрапит JSONL логи
  - Loki индексирует события с label extraction
  - Grafana отображает метрики в реальном времени
- **Makefile команды:**
  - `make obs-up` — запуск Grafana/Loki/Promtail
  - `make obs-down` — остановка
  - `make obs-restart` — перезапуск
  - `make obs-logs` — просмотр логов
- **MANAGE_PROMTAIL flag** для DR smoke tests:
  - `make dr-smoke-truncate MANAGE_PROMTAIL=1`
  - Автоматически останавливает/запускает Promtail для избежания file locking на Windows

### UI «витрина» (`/ui`)
- UI обслуживается самим API как статическая страница: `GET /ui`.
- Реализована корректная постраничная догрузка: UI больше не «застревает» на первых 30 позициях — список подгружается дальше по мере прокрутки.
- По умолчанию включён фильтр **«Только в наличии»** (`in_stock=true`).
- Для изображений SKU используется эндпойнт вида: `/sku/{code}/image` (с фоллбеком на заглушку).
- Для карточки SKU подгружаются детали и (опционально) графики `price-history` и `inventory-history` (Chart.js через CDN; при недоступности CDN UI показывает подсказку вместо графиков).

### Очистка тестовых данных (PostgreSQL)
- Добавлен/уточнён скрипт **`scripts/cleanup_test_data.py`**:
  - Поддерживает работу в режиме **dry-run** (по умолчанию) и **apply** (`--apply`).
  - Читает параметры подключения из `.env` (и/или `PG*`, `DB_*` переменных окружения).
  - Умеет удалять тестовые записи по **prefix** (`--prefix`) и/или по точным **pattern** (`--pattern`).
  - Учитывает FK-зависимости (сначала дочерние таблицы, затем `products`).
- Практика использования:
  - Сначала запуск без `--apply` (смотрим «Planned deletions»),
  - затем запуск с `--apply`.

## Быстрые ссылки внутри репозитория

### Основные точки входа
- UI: `api/templates/ui.html`
- Скрипты: `scripts/`
  - `cleanup_test_data.py` — очистка тестовых данных
  - `emit_event.py` — эмиссия structured events (NEW)
  - `prune_local_backups.py` — очистка локальных бэкапов (NEW)
  - `dr_smoke.ps1` — DR smoke tests с event logging (UPDATED)
  - `minio_backups.py` — MinIO backup management с event logging (UPDATED)
  - `quick_smoke_check.ps1` — быстрые проверки окружения/интеграции
  - `sync_inventory_history.py` — утилиты синхронизации/экспорта истории остатков
- БД и миграции: `db/` и `db/migrations/`

### Observability (NEW)
- Grafana dashboards: `observability/grafana/dashboards/`
  - `wine-assistant-backup-dr.json` — Backup/DR monitoring
  - `wine-assistant-api.json` — API metrics (если есть)
- Promtail config: `observability/promtail-config.yml`
- Loki config: `observability/loki-config.yml`
- Event logs: `logs/backup-dr/` (JSONL format)

### CI/CD
- GitHub workflows: `.github/workflows/`
  - `ci.yml` — тесты и линтеры
  - `semgrep.yml` — security сканирование
  - `secrets.yml` — проверка секретов

## Рекомендованный рабочий процесс

1. **Запуск инфраструктуры:**
   ```bash
   # Базовый стек
   docker compose up -d --build

   # С observability (рекомендуется)
   docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
   # Или через Makefile
   make obs-up
   ```

2. **Проверка базовой работоспособности:**
   - Health endpoints: `curl http://localhost:18000/ready`
   - Поиск: `/api/v1/products/search`
   - Grafana: `http://localhost:15000` (admin/admin)

3. **Проверка UI:**
   - Открыть: `http://localhost:18000/ui`
   - Проверить что список догружается при прокрутке
   - Открыть карточку SKU
   - Проверить графики и изображения

4. **Проверка Observability (NEW):**
   - Открыть Grafana: `http://localhost:15000`
   - Найти Dashboard: "Wine Assistant — Backup & DR"
   - Создать тестовый бэкап: `make backup-local`
   - Обновить Dashboard (auto-refresh 30s)
   - Проверить что панели показывают данные

5. **Backup/DR операции:**
   ```bash
   # Создать бэкап
   make backup-local

   # DR smoke test
   make dr-smoke-truncate MANAGE_PROMTAIL=1

   # Проверить события в Grafana:
   # http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
   ```

6. **Очистка тестовых данных:**
   ```bash
   # Dry-run
   python scripts/cleanup_test_data.py

   # Apply
   python scripts/cleanup_test_data.py --prefix TEST_ --apply
   ```

## Observability: Типичные задачи

### Просмотр backup/DR событий

```powershell
# В Grafana Explore
http://localhost:15000/explore
# LogQL query: {job="wine-backups"}

# Или в файле
Get-Content logs/backup-dr/events.jsonl | Select-Object -Last 20
Get-Content logs/backup-dr/events.jsonl | ConvertFrom-Json | Where-Object { $_.event -eq "backup_local_completed" }
```

### Troubleshooting Grafana

```powershell
# Проверить статус observability stack
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps

# Логи
make obs-logs

# Перезапуск
make obs-restart

# Проверить что Promtail читает логи
docker compose -f docker-compose.yml -f docker-compose.observability.yml logs promtail | Select-String "wine-backups"
```

### Мониторинг бэкапов

```powershell
# Создать тестовый бэкап
make backup-local

# Подождать 30 секунд (auto-refresh)
Start-Sleep 30

# Открыть Dashboard в браузере:
# http://localhost:15000/d/wine-assistant-backup-dr/backup-dr

# Проверить панели:
# - Backups completed (должно увеличиться)
# - Age since last backup (должно быть < 1 минуты)
```

## Документация

### Основная
- **README.md** — главный обзор с архитектурой и примерами
- **QUICK_REFERENCE.md** — шпаргалка команд (включая observability)
- **CHANGELOG.md** — история изменений
- **INDEX.md** — этот файл (навигация)

### Dev документация (`docs/dev/`)
- **backup-dr-runbook.md** — полное руководство по backup/DR с observability секцией
- **web-ui.md** — документация UI
- **windows-powershell-http.md** — PowerShell для API
- **how-to-create-analysis-bundle.md** — создание analysis bundles
- **release-notes-2025-12-21.md** — release notes для backup/DR фич (UPDATED)
- **release-notes-2025-12-22.md** — release notes для observability (если будет создан)

## Полезные ссылки

### Локальные сервисы
- API: http://localhost:18000
- Swagger: http://localhost:18000/docs
- UI: http://localhost:18000/ui
- Adminer: http://localhost:18080
- **Grafana: http://localhost:15000** (admin/admin)
- **Loki Explore: http://localhost:15000/explore**
- **Backup/DR Dashboard: http://localhost:15000/d/wine-assistant-backup-dr/backup-dr**

### External
- GitHub Repo: https://github.com/glinozem/wine-assistant
- GitHub Issues: https://github.com/glinozem/wine-assistant/issues
- Grafana Docs: https://grafana.com/docs/
- Loki LogQL: https://grafana.com/docs/loki/latest/logql/

---

Если вы добавляете новые документы или функциональность — обновляйте этот INDEX, чтобы он оставался «точкой входа» в документацию.

**Last updated:** 2025-12-22 (Added Observability & Monitoring section)
