# Daily import (incremental): implemented changes

## Goal
Provide a repeatable, **incremental** (non-bootstrap) daily import flow for Excel price lists.

Daily import is intended for regular operations:
- take one new Excel price list (usually one file per day);
- update existing products (prices, inventory) and their history;
- insert new products when they appear in the price list;
- keep winery metadata (region/site) aligned via the existing winery-enrichment dataset;
- persist an inventory snapshot for observability.

Bootstrap (`scripts\bootstrap_from_scratch.ps1`) is **not** used for daily work because it wipes volumes and rebuilds a clean environment.

## What was added

### 1) Python orchestrator: `scripts/daily_import.py`
A new orchestrator script implements the daily pipeline while reusing the already-working importer (`scripts.load_csv`).

Supported modes:
- **Auto-inbox (default):** take **only the newest** `.xlsx` file from `data/inbox`.
- **Explicit files list:** pass a list of `.xlsx` files.

Pipeline:
1. Acquire a Postgres advisory lock (prevents parallel runs).
2. For each selected file:
   - Run `python -m scripts.load_csv --excel <file>`.
   - Detect `SKIP` when the same file was already imported (idempotency).
   - **Archive the file even when SKIP** (per decision).
   - On failure: move the file to `data/quarantine/YYYY-MM/`.
3. If at least one file was actually imported (not SKIP):
   - Update wineries catalog: `python -m scripts.load_wineries --excel data/catalog/wineries_enrichment_from_pdf_norm.xlsx --apply`.
   - Enrich products (region/site): `python -m scripts.enrich_producers --excel data/catalog/wineries_enrichment_from_pdf_norm.xlsx --apply`.
   - Run DB maintenance to:
     - sanitize `wineries.producer_site` (remove whitespace);
     - backfill `products.region` from `wineries.region` when missing;
     - backfill `products.producer_site` from `wineries.producer_site` when missing/invalid, with whitespace removal.
   - Create an inventory snapshot: `python -m scripts.sync_inventory_history`.
4. Release the advisory lock.

Idempotency is achieved by the existing `ingest_envelope` mechanism in `scripts.load_csv` (unique by file SHA-256). Re-running daily import on the same file results in `SKIP` and **does not** execute post-import steps (enrichment/snapshot), avoiding duplicate inventory-history snapshots.

### 2) PowerShell wrapper: `scripts/run_daily_import.ps1`
A thin wrapper over the Python orchestrator for Windows usage.

### 3) Makefile targets
Added targets:
- `make daily-import` — auto-inbox (newest file).
- `make daily-import-files FILES="..."` — explicit list.
- `make daily-import-ps1` — PowerShell wrapper alternative.

## How to run

### Option A: Python (recommended; cross-platform)
From project root, with `.env` available (scripts call `load_dotenv()`):

Auto-inbox (newest file only):
```bash
python -m scripts.daily_import --inbox data/inbox
```

Explicit files:
```bash
python -m scripts.daily_import --files data/inbox/2025_12_10.xlsx data/inbox/2025_12_17.xlsx
```

Disable inventory snapshot (rare):
```bash
python -m scripts.daily_import --no-snapshot
```

### Option B: PowerShell wrapper
Auto-inbox:
```powershell
.\scripts\run_daily_import.ps1
```

Explicit files:
```powershell
.\scripts\run_daily_import.ps1 -Files .\data\inbox\2025_12_10.xlsx, .\data\inbox\2025_12_17.xlsx
```

## Operational notes

### Archiving rules
- On **success** and on **SKIP**: file is moved to `data/archive/YYYY-MM/`.
- On **failure**: file is moved to `data/quarantine/YYYY-MM/`.

If a file with the same name already exists in the destination, a numeric suffix is added (`_1`, `_2`, ...).

### Concurrency protection
Daily import takes a Postgres advisory lock identified by a stable key (`wine-assistant:daily-import:v1`).
If the lock cannot be acquired, the run exits with a non-zero exit code.

### Supplier handling
Daily import does **not** ask for a supplier parameter.
Supplier values are extracted from rows by the existing Excel importer (`scripts.load_csv`) exactly as in the primary import flow.

## Files changed / added
- **Added:** `scripts/daily_import.py`
- **Modified:** `scripts/run_daily_import.ps1`
- **Modified:** `Makefile`
- **Added:** `docs/changes_daily_import.md`
