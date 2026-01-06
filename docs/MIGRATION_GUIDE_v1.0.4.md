# Migration Guide: Upgrading to Daily Import (Ops) v1.0.4

**Target Audience:** Developers/operators upgrading from the legacy import scripts to the **Ops Daily Import** workflow
**Effective Date:** January 2026
**Version:** v1.0.4 (Ops)

---

## Overview

This guide helps you migrate to the current **Daily Import (Ops)** implementation, which includes:

- ✅ **Ops API + Web UI** for Daily Import (`/daily-import`)
- ✅ **Deterministic run logs** per run (`data/logs/daily-import/<run_id>.json`)
- ✅ **Two import modes**
  - `auto` — import the newest `.xlsx` from `data/inbox/`
  - `files` — import an explicit list of filenames from `data/inbox/`
- ✅ **Idempotency / SKIP support** (e.g., `ALREADY_IMPORTED_SAME_HASH`)
- ✅ **Windows-friendly UTF-8 runtime** (container locale/env set to UTF-8)
- ✅ Optional **inventory snapshot** post-run (reported in run summary)

---

## Pre-Migration Checklist

Before upgrading, verify:

- [ ] Current Git branch: `master`
- [ ] All local changes committed (or stashed)
- [ ] `.env` configured (at minimum: `API_KEY`, `API_URL`/`API_BASE_URL` if used by tooling)
- [ ] Docker + Docker Compose installed
- [ ] Python 3.11+ installed (for local tools; import itself runs in container)
- [ ] You understand which folder is the **Inbox**: `data/inbox/`

---

## Migration Steps

### Step 1: Update Code

```bash
git checkout master
git pull origin master
git log --oneline -5
```

If your repository previously used `scripts.daily_import` or related legacy wrappers, note that the current workflow uses **`scripts.daily_import_ops`** and/or the **Ops API**.

---

### Step 2: Start the Stack

Bring up DB + API:

```bash
docker compose up -d db api
```

Or via Makefile (recommended):

```bash
make dev-up
```

Confirm API is healthy:

```powershell
irm http://localhost:18000/ready | ConvertTo-Json -Depth 5
```

---

### Step 3: Verify the Ops Daily Import UI & API

#### Web UI
Open in browser:

- `http://localhost:18000/daily-import`

#### Ops API endpoints (require `X-API-Key`)
- `GET /api/v1/ops/daily-import/inbox`
- `POST /api/v1/ops/daily-import/run`
- `GET /api/v1/ops/daily-import/runs/<run_id>`

**PowerShell example:**
```powershell
$k = (Get-Content .\.env | ? { $_ -match '^API_KEY=' } | Select -First 1) -replace '^API_KEY=', ''
$k = $k.Trim()

irm "http://localhost:18000/api/v1/ops/daily-import/inbox" -Headers @{ "X-API-Key" = $k } |
  ConvertTo-Json -Depth 10
```

---

### Step 4: Place Files in Inbox

Put one or more `.xlsx` price lists into:

- `data/inbox/` (host)
- `/app/data/inbox/` (inside `api` container)

Example verification:

```powershell
Get-ChildItem .\data\inbox
docker compose exec api ls -la /app/data/inbox
```

---

### Step 5: Run Daily Import (3 supported methods)

Below are **three** supported ways to execute import operations. On Windows, method **(B)** or **(C)** is recommended for filenames with spaces and Cyrillic.

#### (A) Web UI (recommended for manual ops)

1. Open `http://localhost:18000/daily-import`
2. Paste `X-API-Key` (stored in browser localStorage)
3. Click **Обновить Inbox**
4. Choose import mode and run

Pros:
- Best UX for operators
- Shows run status, per-file results, skip reasons, downloads

---

#### (B) Makefile targets

**Auto mode (newest file):**
```bash
make daily-import
```

**Files mode (explicit list):**
```bash
make daily-import-files FILES="file1.xlsx file2.xlsx"
```

Important notes:
- This target is best for filenames without spaces.
- For Windows and/or filenames with spaces/Cyrillic, use the PowerShell targets below (if present in your Makefile):

```bash
make daily-import-ps
make daily-import-files-ps FILES="2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"
```

---

#### (C) PowerShell wrapper: `scripts/run_daily_import.ps1` (Windows-friendly)

**Auto mode:**
```powershell
.\scripts\run_daily_import.ps1 -Mode auto
```

**Files mode (array):**
```powershell
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс.xlsx","2025_12_25 Другой прайс.xlsx"
```

**Files mode (single CSV string):**
```powershell
.\scripts\run_daily_import.ps1 -Mode files -Files "2025_12_24 Прайс.xlsx,2025_12_25 Другой прайс.xlsx"
```

This wrapper runs the import inside the `api` container via `docker-compose exec` and:
- prints the final JSON (run result),
- returns meaningful exit codes (e.g., non-zero on FAILED/quarantine/no-files/parse error).

---

### Step 6: Review Run History & Details

Run logs are stored in:

- `data/logs/daily-import/<run_id>.json`

Makefile helpers:

```bash
make daily-import-history
make daily-import-show RUN_ID=<uuid>
```

API-based review (PowerShell):

```powershell
$rid = "<uuid>"
irm "http://localhost:18000/api/v1/ops/daily-import/runs/$rid" -Headers @{ "X-API-Key" = $k } |
  ConvertTo-Json -Depth 20
```

---

### Step 7: Verify Inventory Snapshot (if enabled)

The Ops run summary may include:

- `summary.inventory_snapshot.status` (e.g., `DONE`)
- `summary.inventory_snapshot.as_of`

If you need to recompute inventory history manually, use the existing tooling (if available in your project), for example:

```bash
docker compose exec api python -m scripts.sync_inventory_history --dry-run
docker compose exec api python -m scripts.sync_inventory_history
```

---

## Breaking / Behavioral Changes

### 1) Legacy CLI replaced

- **Old:** `python -m scripts.daily_import ...`
- **New:** `python -m scripts.daily_import_ops --mode auto|files ...`, plus Ops API/UI

If you have old scheduled tasks, update them (see below).

### 2) SKIP is first-class

If a file was already imported (same hash), it will be marked `SKIPPED` with a `skip_reason` (e.g., `ALREADY_IMPORTED_SAME_HASH`).

### 3) Files are managed by workflow

Files are expected to be in `data/inbox/` before processing; after processing they may be moved to `data/archive/...` (and/or `data/quarantine/...` if quarantined).

---

## Updating Scheduled Jobs (Windows Task Scheduler)

Example: run **auto mode** daily at 09:00.

```powershell
$taskName = "wine-assistant daily import"
$repoRoot = (Resolve-Path ".").Path
$scriptPath = (Resolve-Path ".\scripts\run_daily_import.ps1").Path

schtasks /Create /TN $taskName /SC DAILY /ST 09:00 /F `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"cd `'$repoRoot`'; & `'$scriptPath`' -Mode auto`""
```

---

## Common Migration Issues

### Issue: `File not found` for a selected file (MANUAL_LIST)

Cause: the UI (or operator) selected a filename that is no longer present in `data/inbox/` (e.g., it was moved to archive by a previous run).

Fix:
- Click **Обновить Inbox** and reselect from the current list
- Prefer the UI, or use the wrapper which is more resilient with filenames

### Issue: Docker orphan containers warning

If you see warnings like “Found orphan containers…”, clean up with:

```bash
docker compose down --remove-orphans
```

### Issue: API returns 403 / unauthorized

Cause: missing/incorrect `X-API-Key`.

Fix: load `API_KEY` from `.env` (see examples above) and retry.

---

## Verification Checklist

After migration, verify:

- [ ] `/daily-import` UI loads
- [ ] `GET /api/v1/ops/daily-import/inbox` returns files list with your key
- [ ] `make daily-import` works (auto mode) when inbox has files
- [ ] Manual list mode imports selected files (or clearly reports missing)
- [ ] Re-running the same file shows `SKIPPED` with a skip reason
- [ ] Archive/quarantine paths are produced as expected
- [ ] Run logs appear in `data/logs/daily-import/`

---

**Migration Guide Version:** v1.0.4 (Ops)
**Last Updated:** January 2026
