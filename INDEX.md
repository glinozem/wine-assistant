# Wine Assistant - Документация

> **Навигация по документации проекта Wine Assistant**

## 📚 Основные документы

### [README.md](README.md)
**Главная документация проекта**
- Обзор возможностей системы
- Быстрый старт (Docker, локальная разработка)
- Архитектура системы
- Import Operations (M1 Complete) 🎉
- Observability & Monitoring
- AI Capabilities (планируется)

### [CHANGELOG.md](CHANGELOG.md)
**История изменений**
- Unreleased: Import Operations M1, Observability, Backup/DR
- Version history (v0.4.3+)
- Bug fixes и improvements

### [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
**Шпаргалка команд**
- Import Operations quick start
- PowerShell примеры для API
- Observability stack (Grafana/Loki/Promtail)
- Backup/DR операции
- Troubleshooting

---

## 📥 Import Operations (M1 Complete)

### [docs/dev/import_flow.md](docs/dev/import_flow.md)
**Архитектура системы импорта**
- Компоненты: Orchestrator, Registry, Stale Detector, Envelope
- Контракт запуска и идемпотентность: `(supplier, as_of_date, file_sha256)`
- Статусы lifecycle: pending → running → success/failed/skipped/rolled_back
- Метрики whitelist: `total_rows_processed`, `rows_skipped`
- Transaction separation (R0.2 contract)
- Envelope semantics и file traceability

### [docs/runbook_import.md](docs/runbook_import.md)
**Operational runbook для импортов**
- Быстрые проверки (последние запуски, staleness)
- Запуск импорта (CLI, PowerShell wrapper)
- Stale detector usage
- Типовые инциденты и решения
- Диагностические SQL queries

---

## 📊 Observability & Monitoring

### [docs/dev/backup-dr-runbook.md](docs/dev/backup-dr-runbook.md)
**Backup/DR operational guide**
- Создание и восстановление бэкапов
- MinIO management
- DR smoke tests
- Promtail integration для Windows
- Troubleshooting
- Event logging в JSONL
- Grafana dashboard setup

### Observability Stack
- **Grafana Dashboard:** http://localhost:15000/d/wine-assistant-backup-dr/backup-dr
- **Loki Explore:** http://localhost:15000/explore
- **Structured Logging:** `logs/backup-dr/events.jsonl`

---

## 🖥️ Web UI

### [docs/dev/web-ui.md](docs/dev/web-ui.md)
**Документация витрины `/ui`**
- Infinite scroll implementation
- API integration
- localStorage для API keys
- Pagination (`limit/offset`)
- Image proxy endpoint

---

## 🔧 Development

### [docs/dev/windows-powershell-http.md](docs/dev/windows-powershell-http.md)
**PowerShell для API разработки**
- `Invoke-RestMethod` vs `curl.exe`
- API key management
- HTTP requests примеры
- JSON parsing
- Error handling

### Development Setup

```bash
# Clone
git clone https://github.com/glinozem/wine-assistant.git
cd wine-assistant

# Setup
cp .env.example .env
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\Activate     # Windows

# Install
pip install -r requirements.txt

# Test
pytest
```

---

## 🗄️ Database

### Migrations
**Location:** `db/migrations/`

**Ключевые миграции:**
- `0014_import_runs.sql` — Import Run Registry (M1)
- `0013_*.sql` — Inventory history tables
- `0012_*.sql` — Wineries reference data

### Views
- `v_import_runs_summary` — сводка по импортам
- `v_import_staleness` — staleness check (hours_since_success)

---

## 🧪 Testing

```bash
# All tests
pytest

# With coverage
pytest --cov=api --cov=scripts --cov-report=html

# Import Operations tests (PowerShell)
$env:RUN_DB_TESTS="1"; pytest tests/unit/test_import_run_registry.py
```

**Coverage:** 175 тестов, >80% coverage

---

## 🔐 Security

### Pre-commit Hooks
```bash
pre-commit install
pre-commit run --all-files
```

### CI/CD Pipeline
- `ci.yml` — pytest, ruff checks
- `semgrep.yml` — security scanning
- `secrets.yml` — secret detection

---

## 📤 API Documentation

### Swagger UI
**URL:** http://localhost:18000/docs

**Key Endpoints:**
- `/api/v1/products/search` — каталог с фильтрацией
- `/api/v1/sku/{code}` — SKU карточка
- `/api/v1/sku/{code}/price-history` — история цен
- `/api/v1/sku/{code}/inventory-history` — история остатков
- `/export/*` — экспорт в JSON/XLSX/PDF
- `/health`, `/ready`, `/live` — health checks

---

## 🛠️ Scripts

### Import Operations
- `scripts/run_import_orchestrator.py` — CLI runner
- `scripts/import_orchestrator.py` — core logic
- `scripts/import_run_registry.py` — registry API
- `scripts/import_targets/run_daily_adapter.py` — legacy ETL adapter
- `scripts/ingest_envelope.py` — file traceability
- `scripts/mark_stale_import_runs.py` — stale detector

### PowerShell Wrappers
- `scripts/run_daily_import.ps1` — daily import automation
- `scripts/run_stale_detector.ps1` — stale cleanup automation

### ETL
- `etl/run_daily.py` — legacy daily import
- `etl/mapping_template.json` — DreemWine mapping config

---

## 📊 Makefile

```bash
# Development
make dev-up / dev-down / dev-logs

# Observability
make obs-up / obs-down / obs-restart / obs-logs

# Backup & DR
make backup-local / restore-local / dr-smoke-truncate

# Storage
make storage-up / backups-list-remote
```

---

## 🏗️ Project Structure

```
wine-assistant/
├── api/                          # Flask application
├── db/migrations/                # SQL migrations
├── docs/
│   ├── dev/
│   │   ├── import_flow.md        # Import architecture
│   │   └── backup-dr-runbook.md  # Backup/DR guide
│   └── runbook_import.md         # Import operations runbook
├── etl/
│   ├── run_daily.py              # Legacy ETL
│   └── mapping_template.json     # DreemWine mapping
├── scripts/
│   ├── import_orchestrator.py    # Import orchestrator core
│   ├── run_daily_import.ps1      # Daily automation
│   └── run_stale_detector.ps1    # Stale cleanup
├── tests/
│   ├── unit/
│   └── integration/
└── README.md
```

---

## 🔗 External Resources

### GitHub
- **Repository:** https://github.com/glinozem/wine-assistant
- **Issues:** https://github.com/glinozem/wine-assistant/issues

### Local Services
- **API:** http://localhost:18000
- **Swagger:** http://localhost:18000/docs
- **UI:** http://localhost:18000/ui
- **Adminer:** http://localhost:18080
- **Grafana:** http://localhost:15000 (admin/admin)

---

## 📝 Documentation Status

| Document | Status | Last Updated | Version |
|----------|--------|--------------|---------|
| README.md | ✅ Current | 2025-12-25 | M1 Complete |
| CHANGELOG.md | ✅ Current | 2025-12-25 | Unreleased |
| QUICK_REFERENCE.md | ✅ Current | 2025-12-25 | v1.2 |
| import_flow.md | ✅ Current | 2025-12-25 | PR-4 |
| runbook_import.md | ✅ Current | 2025-12-25 | PR-4 |
| backup-dr-runbook.md | ✅ Current | 2025-12-22 | v1.0 |

---

## 🎯 Quick Navigation

### For Developers
1. [README.md](README.md) → Quick Start
2. [docs/dev/windows-powershell-http.md](docs/dev/windows-powershell-http.md)
3. Testing: `pytest` commands
4. Pre-commit hooks

### For Operators
1. [README.md](README.md) → Quick Start
2. [docs/runbook_import.md](docs/runbook_import.md) — Import Operations
3. [docs/dev/backup-dr-runbook.md](docs/dev/backup-dr-runbook.md) — Backup/DR
4. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — Commands

### For Users
1. UI: http://localhost:18000/ui
2. API Docs: http://localhost:18000/docs
3. Health: http://localhost:18000/health

---

**Wine Assistant Documentation Index**
**Version:** 1.0
**Last Updated:** 25 декабря 2025
**Status:** M1 (Import Operations) Complete 🎉
