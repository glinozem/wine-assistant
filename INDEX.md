# Wine Assistant - Документация


## 📥 Ops Daily Import (Current)

- UI: `/daily-import`
- API:
  - `GET /api/v1/ops/daily-import/inbox`
  - `POST /api/v1/ops/daily-import/run`
  - `GET /api/v1/ops/daily-import/runs/<run_id>`
- CLI / Dev:
  - Makefile: `make daily-import`, `make daily-import-files`, `make daily-import-files-ps`, `make daily-import-history`
  - PowerShell: `scripts/run_daily_import.ps1`
- Runbook: `runbook_import.md`
## 📚 Основные документы

### [README.md](README.md)
**Главная документация проекта**
- Обзор возможностей системы
- Быстрый старт (Docker, локальная разработка)
- Архитектура системы
- Import Operations (M1 Complete) 🎉
- Ops Daily Import (Incremental) 🎉
- Observability & Monitoring
- AI Capabilities (планируется)

### [CHANGELOG.md](CHANGELOG.md)
**История изменений**
- Unreleased: Ops Daily Import, Import Operations M1, Observability, Backup/DR
- Version history (v0.4.3+)
- Bug fixes и improvements
- **Latest:** v1.0.4 bugfix (UnicodeEncodeError) + infrastructure

### [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
**Шпаргалка команд**
- **Ops Daily Import** — incremental import quick start
- Import Operations (legacy orchestrator)
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

**Recent Schema Changes (v1.0.4):**
- `products.supplier` — supplier normalization field
- `products.price_list_rub` — list price
- `products.price_final_rub` — final price with discount
- `inventory.stock_total`, `inventory.reserved`, `inventory.stock_free`
- `inventory_history` — idempotent daily snapshots

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

# Daily import smoke test
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1
```

**Coverage:** 175+ тестов, >80% coverage

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

### Daily Import (Ops)

- **`scripts/daily_import_ops.py`** — orchestrator для Ops Daily Import
  - `--mode auto`: берёт самый новый `.xlsx` из `data/inbox/`
  - `--mode files --files ...`: обрабатывает выбранные имена файлов (точное совпадение с inbox)
  - Ведение run JSON + summary, архивация в `data/archive/`, quarantine в `data/quarantine/`
- **`scripts/run_daily_import.ps1`** — Windows-friendly wrapper (mode auto/files)
- **`api/templates/daily_import.html`** — UI страница (`/daily-import`)
### Import Operations (Legacy)
- `scripts/run_import_orchestrator.py` — CLI runner
- `scripts/import_orchestrator.py` — core logic
- `scripts/import_run_registry.py` — registry API
- `scripts/import_targets/run_daily_adapter.py` — legacy ETL adapter
- `scripts/ingest_envelope.py` — file traceability
- `scripts/mark_stale_import_runs.py` — stale detector

### ETL
- `etl/run_daily.py` — daily import ETL (with inventory tracking)
- `etl/mapping_template.json` — DreemWine mapping config

### Common Scripts
- `scripts/load_wineries.py` — wineries catalog (with safe_print v1.0.4)
- `scripts/enrich_producers.py` — product enrichment (with safe_print v1.0.4)
- `scripts/sync_inventory_history.py` — inventory snapshots (with safe_print v1.0.4)

---

## 📊 Makefile

### Daily Import
```bash
make daily-import                  # Auto-inbox (newest file)
make daily-import-files FILES="..."  # Explicit files
make daily-import-ps1              # PowerShell wrapper
make sync-inventory-history AS_OF="2025-12-31"  # Manual snapshot
```

### Development
```bash
make dev-up / dev-down / dev-logs
```

### Observability
```bash
make obs-up / obs-down / obs-restart / obs-logs
```

### Backup & DR
```bash
make backup-local / restore-local / dr-smoke-truncate
```

### Testing
```bash
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1
```

### Storage
```bash
make storage-up / backups-list-remote
```

---

## 🏗️ Project Structure

```
wine-assistant/
├── api/                          # Flask application
├── db/migrations/                # SQL migrations
│   ├── 0014_import_runs.sql      # Import registry (M1)
│   └── 0013_*.sql                # Inventory tables
├── docs/
│   ├── changes_daily_import.md   # Ops Daily Import docs
│   ├── dev/
│   │   ├── import_flow.md        # Import architecture
│   │   └── backup-dr-runbook.md  # Backup/DR guide
│   └── runbook_import.md         # Import operations runbook
├── etl/
│   ├── run_daily.py              # Daily ETL (inventory + supplier)
│   └── mapping_template.json     # DreemWine mapping
├── scripts/
│   ├── daily_import_ops.py           # Daily import orchestrator ⭐ NEW
│   ├── bootstrap_from_scratch.ps1  # Fresh deployment ⭐ NEW
│   ├── smoke_e2e.ps1             # E2E testing ⭐ NEW
│   ├── run_daily_import.ps1      # PowerShell wrapper (rewritten)
│   ├── load_wineries.py          # Wineries (safe_print v1.0.4)
│   ├── enrich_producers.py       # Enrichment (safe_print v1.0.4)
│   ├── sync_inventory_history.py # Snapshots (safe_print v1.0.4)
│   ├── import_orchestrator.py    # Import orchestrator core
│   └── run_stale_detector.ps1    # Stale cleanup
├── tests/
│   ├── unit/
│   └── integration/
├── CHANGELOG.md                   # Updated with v1.0.4
├── QUICK_REFERENCE.md             # Updated with daily import
├── INDEX.md                       # This file
└── README.md                      # Main documentation
```

---

## 🔗 External Resources

### GitHub
- **Repository:** https://github.com/glinozem/wine-assistant
- **Issues:** https://github.com/glinozem/wine-assistant/issues
- **Latest Release:** v1.0.4 (Daily Import Bugfix)
- **PR #172:** UnicodeEncodeError fix
- **PR #173:** Infrastructure + ETL + testing

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
| README.md | ✅ Current | 2025-12-31 | v1.0.4 |
| CHANGELOG.md | ✅ Current | 2025-12-31 | v1.0.4 |
| QUICK_REFERENCE.md | ✅ Current | 2025-12-31 | v2.0 |
| changes_daily_import.md | ✅ Current | 2025-12-31 | v1.0.4 |
| import_flow.md | ✅ Current | 2025-12-25 | PR-4 |
| runbook_import.md | ✅ Current | 2025-12-25 | PR-4 |
| backup-dr-runbook.md | ✅ Current | 2025-12-22 | v1.0 |

---

## 🎯 Quick Navigation

### For Developers
1. [README.md](README.md) → Quick Start
2. [docs/changes_daily_import.md](docs/changes_daily_import.md) → Daily Import architecture
3. [docs/dev/windows-powershell-http.md](docs/dev/windows-powershell-http.md)
4. Testing: `pytest` commands
5. Pre-commit hooks

### For Operators
1. [README.md](README.md) → Quick Start
2. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — Commands cheat sheet
3. [docs/changes_daily_import.md](docs/changes_daily_import.md) — Daily Import guide
4. [docs/runbook_import.md](docs/runbook_import.md) — Import Operations
5. [docs/dev/backup-dr-runbook.md](docs/dev/backup-dr-runbook.md) — Backup/DR

### For Users
1. UI: http://localhost:18000/ui
2. API Docs: http://localhost:18000/docs
3. Health: http://localhost:18000/health

---

## 🚀 What's New in v1.0.4

### Bugfix: UnicodeEncodeError (PR #172)
- ✅ Fixed Windows CP1251 console crashes
- ✅ Added `safe_print()` to 4 scripts
- ✅ 15+ successful production test runs
- ✅ Tag: v1.0.4

### Infrastructure & ETL (PR #173)
- ✅ Daily import orchestrator (`scripts/daily_import.py`)
- ✅ Inventory tracking (stock_total, reserved, stock_free)
- ✅ Supplier normalization (`products.supplier` field)
- ✅ Extended price tracking (list/final/current prices)
- ✅ Bootstrap script (`bootstrap_from_scratch.ps1`)
- ✅ E2E smoke test (`smoke_e2e.ps1`)
- ✅ Makefile targets for daily import
- ✅ PowerShell wrapper rewritten (214→64 lines)

### Key Benefits
- 📈 **Incremental imports** — no volume wiping
- 🔄 **Idempotent** — safe to re-run
- 📊 **Inventory history** — full tracking
- 🖥️ **Windows-friendly** — encoding issues resolved
- 🔒 **Concurrency protection** — advisory locks
- 📁 **Smart archiving** — automatic file management

---

## 📖 Documentation Guides

### Getting Started
1. **Installation:** README.md → Quick Start
2. **First Import:** QUICK_REFERENCE.md → Daily Import
3. **Troubleshooting:** docs/changes_daily_import.md → Troubleshooting section

### Daily Operations
1. **Run Import:** `make daily-import`
2. **Check Status:** SQL queries in QUICK_REFERENCE.md
3. **Monitor:** Grafana dashboard

### Advanced Topics
1. **Import Architecture:** docs/dev/import_flow.md
2. **ETL Details:** docs/changes_daily_import.md
3. **Backup/DR:** docs/dev/backup-dr-runbook.md

---

**Wine Assistant Documentation Index**
**Version:** 2.0
**Last Updated:** 31 декабря 2025
**Status:** Ops Daily Import available ✅
**Milestone:** M1 (Import Operations) + v1.0.4 (Incremental Daily Import)
