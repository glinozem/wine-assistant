# Daily Import v1.0.4: Implementation & Changes

## Overview

Daily Import v1.0.4 provides a production-ready, incremental import solution for daily price list updates.

**Key Improvements:**
- ✅ **UnicodeEncodeError fixed** — Windows CP1251 encoding handled correctly
- ✅ **Incremental imports** — no volume wiping required
- ✅ **Inventory tracking** — automatic snapshots with history
- ✅ **Extended ETL** — supplier normalization, price tracking, stock management
- ✅ **Automation scripts** — bootstrap and smoke testing

---

## Version: v1.0.4 (Production Ready)

**Release Date:** December 31, 2025
**Status:** ✅ Stable
**PRs:** #172 (bugfix), #173 (infrastructure + ETL)

---

## Goal

Provide a repeatable, **incremental** (non-bootstrap) daily import flow for Excel price lists.

Daily import is intended for regular operations:
- Take one new Excel price list (usually one file per day)
- Update existing products (prices, inventory) and their history
- Insert new products when they appear in the price list
- Keep winery metadata (region/site) aligned via the existing winery-enrichment dataset
- Persist an inventory snapshot for observability
- **Handle Windows console encoding issues** (v1.0.4 fix)

Bootstrap (`scripts\bootstrap_from_scratch.ps1`) is **not** used for daily work because it wipes volumes and rebuilds a clean environment.

---

## What was Added

### 1) Bugfix v1.0.4: UnicodeEncodeError Resolution

**Problem:**
Windows console (CP1251 encoding) crashes when printing Unicode characters (Cyrillic, emoji) during import operations.

**Solution:**
Added `safe_print()` function to all affected scripts:

**Files Modified:**
- `scripts/daily_import.py` (new file)
- `scripts/load_wineries.py`
- `scripts/enrich_producers.py`
- `scripts/sync_inventory_history.py`

**Implementation:**
```python
import builtins

def safe_print(*args, **kwargs):
    """Safe print that handles UnicodeEncodeError on Windows console (CP1251)"""
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        message = ' '.join(str(arg) for arg in args)
        safe_message = message.encode('cp1251', errors='replace').decode('cp1251')
        builtins.print(safe_message, **kwargs)
```

**Result:**
- ✅ No crashes on Windows
- ✅ Emoji displays as `?` (expected CP1251 behavior)
- ✅ 15+ consecutive successful test runs
- ✅ Exit code: 0 in all tests

---

### 2) Python Orchestrator: `scripts/daily_import.py`

A new orchestrator script implements the daily pipeline while reusing the already-working importer (`scripts.load_csv`).

**Supported Modes:**
- **Auto-inbox (default):** take **only the newest** `.xlsx` file from `data/inbox`
- **Explicit files list:** pass a list of `.xlsx` files

**Pipeline Steps:**
1. Acquire a Postgres advisory lock (prevents parallel runs)
2. For each selected file:
   - Run `python -m scripts.load_csv --excel <file>`
   - Detect `SKIP` when the same file was already imported (idempotency)
   - **Archive the file even when SKIP** (per decision)
   - On failure: move the file to `data/quarantine/YYYY-MM/`
3. If at least one file was actually imported (not SKIP):
   - Update wineries catalog: `python -m scripts.load_wineries --excel data/catalog/wineries_enrichment_from_pdf_norm.xlsx --apply`
   - Enrich products (region/site): `python -m scripts.enrich_producers --excel data/catalog/wineries_enrichment_from_pdf_norm.xlsx --apply`
   - Run DB maintenance to:
     - Sanitize `wineries.producer_site` (remove whitespace)
     - Backfill `products.region` from `wineries.region` when missing
     - Backfill `products.producer_site` from `wineries.producer_site` when missing/invalid, with whitespace removal
   - Create an inventory snapshot: `python -m scripts.sync_inventory_history`
4. Release the advisory lock

**Idempotency:**
Achieved by the existing `ingest_envelope` mechanism in `scripts.load_csv` (unique by file SHA-256). Re-running daily import on the same file results in `SKIP` and **does not** execute post-import steps (enrichment/snapshot), avoiding duplicate inventory-history snapshots.

---

### 3) ETL & Inventory Enhancements: `etl/run_daily.py`

**Inventory Tracking:**
- New function `upsert_inventory()` for inventory snapshots
- Columns: `stock_total`, `reserved`, `stock_free`
- Upsert logic: updates `inventory` table on each import
- Idempotent snapshots to `inventory_history` (one per date)
- Auto-calculation: `stock_free = stock_total - reserved` when missing

**Supplier Normalization:**
- New field: `supplier` in products table
- Function `norm_supplier_key()` for supplier key normalization
- Fallback logic: supplier → producer if not specified

**Extended Price Tracking:**
- `price_list_rub` — list price from supplier
- `price_final_rub` — final price with discount
- `price_rub` — current price (backward compatibility)
- Fallback logic between fields

**Price History:**
- Existing `product_prices` table tracks price changes
- Closes previous price interval when price changes
- Opens new interval with new price

**Mapping Template Updates:**
`etl/mapping_template.json` extended with:
```json
{
  "supplier": "Поставщик",
  "price_list_rub": "Цена\nпрайс",
  "price_final_rub": "Цена со скидкой",
  "stock_total": "остатки",
  "reserved": "резерв",
  "stock_free": "свободный остаток"
}
```

---

### 4) PowerShell Wrapper: `scripts/run_daily_import.ps1`

Completely rewritten as a thin wrapper over the Python orchestrator.

**Before:** 214 lines with complex file discovery logic
**After:** 64 lines, delegates to `python -m scripts.daily_import`

**Parameters:**
- `-Files` — explicit file list
- `-InboxPath` — custom inbox directory (default: `data\inbox`)
- `-ArchivePath` — custom archive directory (default: `data\archive`)
- `-QuarantinePath` — custom quarantine directory (default: `data\quarantine`)
- `-NoSnapshot` — skip inventory snapshot
- `-SnapshotDryRunFirst` — run snapshot in dry-run mode first

---

### 5) Makefile Targets

Added targets for daily import workflow:

```makefile
# Auto-inbox: take ONLY the newest .xlsx from data/inbox
make daily-import

# Explicit files list
make daily-import-files FILES="data/inbox/a.xlsx data/inbox/b.xlsx"

# Windows PowerShell wrapper (alternative)
make daily-import-ps1
make daily-import-ps1 FILES="data\\inbox\\a.xlsx"

# Inventory snapshot with custom date
make sync-inventory-history AS_OF="2025-12-31"
make sync-inventory-history-dry-run AS_OF="2025-12-31"
```

---

### 6) Bootstrap & Testing Scripts

**`scripts/bootstrap_from_scratch.ps1`**
Automated fresh deployment:
- Wipes volumes (`docker compose down -v`)
- Builds images
- Starts services
- Waits for API readiness
- Imports all price lists from inbox (sorted by date)
- Loads wineries catalog
- Enriches products
- Backfills region and producer_site
- Creates inventory snapshot
- Runs verification checks

**Usage:**
```powershell
.\scripts\bootstrap_from_scratch.ps1 -RebuildImages
```

**`scripts/smoke_e2e.ps1`**
End-to-end smoke testing:
- Orchestrates full import workflow
- Validates data integrity
- Fresh mode support (wipe volumes)
- Configurable stale detector
- Optional API smoke tests
- SQL validation checks

**Usage:**
```powershell
# Via Makefile
make smoke-e2e SMOKE_SUPPLIER=dreemwine SMOKE_FRESH=1

# Direct PowerShell
.\scripts\smoke_e2e.ps1 -Supplier dreemwine -Fresh -Build
```

---

## How to Run

### Option A: Python (recommended; cross-platform)

From project root, with `.env` available (scripts call `load_dotenv()`):

**Auto-inbox (newest file only):**
```bash
python -m scripts.daily_import --inbox data/inbox
```

**Explicit files:**
```bash
python -m scripts.daily_import --files data/inbox/2025_12_10.xlsx data/inbox/2025_12_17.xlsx
```

**Disable inventory snapshot (rare):**
```bash
python -m scripts.daily_import --no-snapshot
```

**Custom directories:**
```bash
python -m scripts.daily_import \
  --inbox data/inbox \
  --archive data/archive \
  --quarantine data/quarantine
```

---

### Option B: PowerShell Wrapper

**Auto-inbox:**
```powershell
.\scripts\run_daily_import.ps1
```

**Explicit files:**
```powershell
.\scripts\run_daily_import.ps1 -Files .\data\inbox\2025_12_10.xlsx, .\data\inbox\2025_12_17.xlsx
```

**Custom paths:**
```powershell
.\scripts\run_daily_import.ps1 -InboxPath "D:\imports\inbox"
```

**Dry-run snapshot first:**
```powershell
.\scripts\run_daily_import.ps1 -SnapshotDryRunFirst
```

---

### Option C: Makefile

**Auto-inbox:**
```bash
make daily-import
```

**Explicit files:**
```bash
make daily-import-files FILES="data/inbox/file1.xlsx data/inbox/file2.xlsx"
```

**PowerShell wrapper:**
```bash
make daily-import-ps1
```

---

## Operational Notes

### Archiving Rules

- **On success and on SKIP:** file is moved to `data/archive/YYYY-MM/`
- **On failure:** file is moved to `data/quarantine/YYYY-MM/`

If a file with the same name already exists in the destination, a numeric suffix is added (`_1`, `_2`, ...).

---

### Concurrency Protection

Daily import takes a Postgres advisory lock identified by a stable key (`wine-assistant:daily-import:v1`).

If the lock cannot be acquired, the run exits with a non-zero exit code.

**Check locks:**
```sql
SELECT * FROM pg_locks WHERE locktype = 'advisory';
```

**Release stuck locks:**
```sql
SELECT pg_advisory_unlock_all();
```

---

### Supplier Handling

Daily import does **not** ask for a supplier parameter.

Supplier values are extracted from rows by the existing Excel importer (`scripts.load_csv`) exactly as in the primary import flow.

The new `supplier` field in products table is populated via `norm_supplier_key()` normalization.

---

### Inventory Snapshot Behavior

**Default:** Creates inventory snapshot after successful import.

**Idempotent:** One snapshot per date (`as_of::date`).

**Skip on SKIP:** If file was already imported (SKIP), snapshot is not created.

**Disable:** Use `--no-snapshot` flag to skip snapshot creation.

**Custom date:** Use `make sync-inventory-history AS_OF="2025-12-31"` for manual snapshot.

---

### Expected Output

**Successful run:**
```
=== IMPORT (load_csv) ===
>>> File: data\inbox\2025_12_12 Прайс_Легенда_Виноделия.xlsx
[OK] Import completed successfully
[daily-import] Moved: data\inbox\*.xlsx -> data\archive\2025-12\*.xlsx

=== LOAD WINERIES CATALOG ===
Готово. Вставлено новых записей: 0, обновлено существующих: 46

=== ENRICH PRODUCTS ===
Готово. Всего затронуто строк в products: 244

=== MAINTENANCE SQL ===
[daily-import] Maintenance SQL completed

=== INVENTORY HISTORY SNAPSHOT ===
[OK] Вставлено 270 записей в public.inventory_history

=== SUMMARY ===
- IMPORTED 2025_12_12 Прайс_Легенда_Виноделия.xlsx -> data\archive\2025-12\*

Exit code: 0
```

**SKIP (idempotent):**
```
=== IMPORT (load_csv) ===
>> SKIP: File already imported
[daily-import] Moved: data\inbox\*.xlsx -> data\archive\2025-12\*.xlsx

=== SUMMARY ===
- SKIPPED (already imported)

Exit code: 0
```

---

## Files Changed / Added

### Added
- `scripts/daily_import.py` — orchestrator
- `scripts/bootstrap_from_scratch.ps1` — fresh deployment automation
- `scripts/smoke_e2e.ps1` — E2E testing
- `docs/changes_daily_import.md` — this document

### Modified
- `scripts/run_daily_import.ps1` — rewritten as thin wrapper (214→64 lines)
- `scripts/load_wineries.py` — added safe_print()
- `scripts/enrich_producers.py` — added safe_print()
- `scripts/sync_inventory_history.py` — added safe_print()
- `etl/run_daily.py` — inventory tracking, supplier normalization, extended prices
- `etl/mapping_template.json` — new fields (supplier, prices, stock)
- `Makefile` — daily-import targets, sync-inventory-history targets, smoke-e2e target

---

## Testing

**v1.0.4 Validation:**
- ✅ 15+ consecutive successful runs
- ✅ Idempotency confirmed (re-running on same files is safe)
- ✅ All import stages complete without errors
- ✅ No UnicodeEncodeError on Windows CP1251 console
- ✅ Exit code: 0 in all tests
- ✅ Inventory snapshots working correctly

**Inventory Tracking:**
- ✅ `inventory` table updated on each import
- ✅ `inventory_history` snapshots created correctly
- ✅ Idempotent: one snapshot per date
- ✅ Stock calculations working (stock_free = stock_total - reserved)

**Bootstrap & Smoke Tests:**
- ✅ Bootstrap script verified on fresh deployment
- ✅ Smoke test passing end-to-end
- ✅ SQL validation checks passing

---

## Known Limitations

**Console Encoding:**
- Emoji displays as `?` on Windows CP1251 console (expected behavior)
- Workaround: `chcp 65001` before running scripts (switch to UTF-8)
- Or use UTF-8 terminal (e.g., Windows Terminal)

**Advisory Lock:**
- Single instance only (design decision to prevent race conditions)
- If lock cannot be acquired, script exits with error

**File Format:**
- Only `.xlsx` files supported
- CSV/XLS not supported

---

## Migration Notes

**From Previous Versions:**
If upgrading from earlier daily import implementations:

1. **Delete old bugfix files** (v1.0.0 - v1.0.3 if present)
2. **Extract v1.0.4**
3. **Copy all 4 files** (critical: don't skip sync_inventory_history.py!)
4. **Test:** `python -m scripts.daily_import --dry-run`

**Database Schema:**
No breaking changes. New columns are added via existing migration system.

---

## Troubleshooting

**Problem: UnicodeEncodeError**
```
Solution: Ensure all 4 files have v1.0.4 safe_print() implementation
Check: grep "def safe_print" scripts/*.py
```

**Problem: Import stuck**
```
Solution: Check advisory locks
SQL: SELECT * FROM pg_locks WHERE locktype = 'advisory';
Release: SELECT pg_advisory_unlock_all();
```

**Problem: Inventory snapshot not created**
```
Cause: File was SKIP (already imported)
Solution: Normal behavior - snapshot only on actual import
Override: make sync-inventory-history AS_OF="2025-12-31"
```

**Problem: File in quarantine**
```
Cause: Import failed
Solution: Check file in data/quarantine/YYYY-MM/
Review: Error logs for details
Fix: Correct data/mapping issue
Retry: Move file back to inbox, run again
```

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| v1.0.4 | 2025-12-31 | ✅ Stable | Production ready |
| v1.0.3 | 2025-12-31 | ⚠️ Incomplete | Missing sync fix |
| v1.0.2 | 2025-12-31 | ❌ Broken | TypeError |
| v1.0.1 | 2025-12-31 | ❌ Broken | RecursionError |
| v1.0.0 | 2025-12-31 | ❌ Broken | Initial issues |

**Use v1.0.4 in production.**

---

## Support

For issues or questions:
1. Check this documentation
2. Review CHANGELOG.md for version details
3. Verify all 4 files are v1.0.4
4. Check exit code: should be 0
5. Review logs for errors

---

**Last Updated:** December 31, 2025
**Version:** v1.0.4
**Status:** Production Ready
**Maintained By:** Wine Assistant Development Team
