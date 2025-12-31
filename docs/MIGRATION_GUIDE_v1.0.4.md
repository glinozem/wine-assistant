# Migration Guide: Upgrading to Daily Import v1.0.4

**Target Audience:** Users upgrading from previous import implementations
**Effective Date:** December 31, 2025
**Version:** v1.0.4

---

## Overview

This guide helps you migrate to Daily Import v1.0.4, which includes:
- ✅ UnicodeEncodeError fix (Windows CP1251)
- ✅ Incremental import infrastructure
- ✅ Inventory tracking with history
- ✅ Supplier normalization
- ✅ Extended price tracking

---

## Pre-Migration Checklist

Before upgrading, verify:

- [ ] Current Git branch: `master`
- [ ] All local changes committed
- [ ] Database backup created
- [ ] .env file configured
- [ ] Python 3.11+ installed
- [ ] Docker and Docker Compose available

---

## Migration Steps

### Step 1: Update Code

```bash
# Pull latest changes
git checkout master
git pull origin master

# Verify you have the latest
git log --oneline -5
# Should show commits for v1.0.4 and PR #172, #173
```

**Expected commits:**
```
<hash> feat(scripts): add bootstrap and smoke test scripts
<hash> feat(daily-import): add incremental import infrastructure
<hash> fix(daily-import): resolve UnicodeEncodeError (v1.0.4)
```

### Step 2: Verify File Changes

**Check that all 4 files have safe_print():**
```bash
# Windows (PowerShell)
Get-ChildItem scripts\daily_import.py, scripts\load_wineries.py, scripts\enrich_producers.py, scripts\sync_inventory_history.py | ForEach-Object { Select-String -Path $_.FullName -Pattern "def safe_print" }

# Linux/Mac
grep -l "def safe_print" scripts/daily_import.py scripts/load_wineries.py scripts/enrich_producers.py scripts/sync_inventory_history.py
```

**Should return all 4 files.** If not, you don't have v1.0.4.

### Step 3: Database Schema Updates

**Check if migrations are needed:**
```bash
# Connect to database
docker compose exec -T db psql -U postgres -d wine_db

# Check for new columns
\d products
# Should have: supplier, price_list_rub, price_final_rub

\d inventory
# Should have: stock_total, reserved, stock_free, asof_date

\d inventory_history
# Should have: as_of, code, stock_total, reserved, stock_free
```

**If columns are missing**, apply migrations:
```bash
# Apply pending migrations
docker compose exec -T db psql -U postgres -d wine_db -f /migrations/0013_inventory_tables.sql
# (Adjust migration files as needed)
```

### Step 4: Update ETL Configuration

**Verify mapping template:**
```bash
cat etl/mapping_template.json
```

**Should include:**
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

**If missing**, update `etl/mapping_template.json` with new fields.

### Step 5: Test Daily Import

**Dry-run test (no actual import):**
```bash
# Check file selection
python -m scripts.daily_import --inbox data/inbox --help

# Verify command works
python -m scripts.daily_import --files data/inbox/test_file.xlsx
# (Use an already-imported file to test SKIP behavior)
```

**Expected output for SKIP:**
```
=== IMPORT (load_csv) ===
>> SKIP: File already imported
[daily-import] Moved: data\inbox\*.xlsx -> data\archive\2025-12\*.xlsx

Exit code: 0
```

### Step 6: Test Inventory Snapshot

**Create a snapshot:**
```bash
# Dry-run first
python -m scripts.sync_inventory_history --dry-run

# Actual snapshot
python -m scripts.sync_inventory_history
```

**Expected output:**
```
[OK] Вставлено <N> записей в public.inventory_history для as_of=<timestamp>
```

**Verify in database:**
```sql
SELECT COUNT(*), MAX(as_of), MIN(as_of)
FROM inventory_history;
```

### Step 7: Update Automation Scripts

**If you have scheduled tasks**, update them:

**Windows Task Scheduler:**
```powershell
# Remove old task (if exists)
schtasks /Delete /TN "wine-assistant old import" /F

# Create new task
$taskName = "wine-assistant daily import"
$scriptPath = (Resolve-Path ".\scripts\run_daily_import.ps1").Path
schtasks /Create /TN $taskName /SC DAILY /ST 09:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" /F
```

**Linux Cron:**
```bash
# Edit crontab
crontab -e

# Replace old line with:
0 9 * * * cd /opt/wine-assistant && .venv/bin/python -m scripts.daily_import
```

### Step 8: Verify Full Pipeline

**Run complete pipeline:**
```bash
# Place a new file in inbox
cp /path/to/new_price_list.xlsx data/inbox/

# Run daily import
make daily-import

# Verify exit code
echo $?  # Should be 0

# Check results
docker compose exec -T db psql -U postgres -d wine_db -c "
SELECT run_id, supplier, as_of_date, status, total_rows_processed
FROM import_runs
ORDER BY created_at DESC
LIMIT 1;"
```

---

## Breaking Changes

**None.** v1.0.4 is fully backward compatible.

**Behavioral Changes:**
1. **Emoji display:** On Windows CP1251 console, emoji shows as `?` (expected)
2. **File archiving:** Now archives even on SKIP (was: only on success)
3. **Inventory snapshots:** Created automatically after successful import

---

## Rollback Procedure

If you need to rollback:

### Option 1: Git Revert

```bash
# Revert to previous commit
git log --oneline -5
git revert <commit_hash_of_v1.0.4>
git push origin master
```

### Option 2: Restore from Backup

```bash
# Restore database
make restore-local FILE=backups/wine_db_before_v1.0.4.dump

# Restore code
git checkout <previous_commit_hash>
```

### Option 3: Manual Rollback

```bash
# Restore old scripts (if you have backups)
cp backups/load_wineries.py.old scripts/load_wineries.py
cp backups/enrich_producers.py.old scripts/enrich_producers.py
cp backups/sync_inventory_history.py.old scripts/sync_inventory_history.py

# Remove new files
rm scripts/daily_import.py
rm scripts/bootstrap_from_scratch.ps1
rm scripts/smoke_e2e.ps1
```

---

## Verification Checklist

After migration, verify:

- [ ] `make daily-import` completes successfully (exit code 0)
- [ ] No UnicodeEncodeError on Windows console
- [ ] Inventory snapshots created in `inventory_history`
- [ ] Files archived correctly to `data/archive/YYYY-MM/`
- [ ] Idempotency works (re-running shows SKIP)
- [ ] Products have `supplier` field populated
- [ ] Inventory has `stock_total`, `reserved`, `stock_free`
- [ ] Price history tracking works
- [ ] Scheduled tasks updated (if using automation)

---

## Common Migration Issues

### Issue: UnicodeEncodeError still occurs

**Cause:** Not all 4 files updated to v1.0.4

**Solution:**
```bash
# Verify all 4 files
grep -c "def safe_print" scripts/daily_import.py
grep -c "def safe_print" scripts/load_wineries.py
grep -c "def safe_print" scripts/enrich_producers.py
grep -c "def safe_print" scripts/sync_inventory_history.py

# Each should return: 1
# If not, git pull and check again
```

### Issue: Missing columns in database

**Cause:** Migrations not applied

**Solution:**
```bash
# Apply migrations
docker compose exec -T db psql -U postgres -d wine_db

# Add missing columns (example)
ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_list_rub NUMERIC(10,2);
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_final_rub NUMERIC(10,2);

ALTER TABLE inventory ADD COLUMN IF NOT EXISTS stock_total NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS reserved NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS stock_free NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE inventory ADD COLUMN IF NOT EXISTS asof_date DATE;
```

### Issue: Advisory lock stuck

**Cause:** Previous import crashed without releasing lock

**Solution:**
```sql
-- Release all advisory locks
SELECT pg_advisory_unlock_all();
```

### Issue: Inventory snapshot fails

**Cause:** Table structure mismatch

**Solution:**
```bash
# Verify table exists
docker compose exec -T db psql -U postgres -d wine_db -c "\d inventory_history"

# If missing, create table
docker compose exec -T db psql -U postgres -d wine_db -c "
CREATE TABLE IF NOT EXISTS inventory_history (
    id SERIAL PRIMARY KEY,
    as_of TIMESTAMPTZ NOT NULL,
    code TEXT NOT NULL,
    stock_total NUMERIC(10,2) NOT NULL DEFAULT 0,
    reserved NUMERIC(10,2) NOT NULL DEFAULT 0,
    stock_free NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inventory_history_code_asof
ON inventory_history(code, as_of);

CREATE INDEX IF NOT EXISTS idx_inventory_history_asof
ON inventory_history(as_of);
"
```

---

## Post-Migration Tasks

### 1. Monitor First Imports

```bash
# Watch logs during first import
python -m scripts.daily_import --inbox data/inbox 2>&1 | tee first_import.log

# Review log
cat first_import.log
```

### 2. Verify Data Integrity

```sql
-- Products with inventory
SELECT COUNT(*) FROM products WHERE supplier IS NOT NULL;

-- Inventory snapshots
SELECT COUNT(*), MAX(as_of) FROM inventory_history;

-- Price history
SELECT COUNT(*) FROM product_prices;
```

### 3. Update Documentation

```bash
# Update team wiki/docs
# Add new daily import procedures
# Share QUICK_REFERENCE.md with team
```

### 4. Set Up Monitoring

```sql
-- Create view for daily monitoring
CREATE OR REPLACE VIEW v_daily_import_health AS
SELECT
    DATE(created_at) as import_date,
    COUNT(*) as total_runs,
    COUNT(*) FILTER (WHERE status = 'success') as successful,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    COUNT(*) FILTER (WHERE status = 'skipped') as skipped,
    SUM(total_rows_processed) as total_rows
FROM import_runs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY import_date DESC;

-- Query it daily
SELECT * FROM v_daily_import_health;
```

---

## Support

If you encounter issues during migration:

1. **Check Logs:** Review `first_import.log`
2. **Verify Files:** Ensure all 4 files have v1.0.4
3. **Database Schema:** Verify all columns exist
4. **Test Isolation:** Test on a copy/staging environment first
5. **Rollback:** Use rollback procedure if needed
6. **Documentation:** Review [docs/changes_daily_import.md](docs/changes_daily_import.md)

---

## Success Criteria

Migration is successful when:

- ✅ `make daily-import` completes with exit code 0
- ✅ No encoding errors on Windows
- ✅ Inventory snapshots created automatically
- ✅ Files archived correctly
- ✅ Database queries return expected results
- ✅ Automation (cron/scheduled tasks) works
- ✅ Team trained on new workflow

---

## Next Steps

After successful migration:

1. **Run Daily:** Use `make daily-import` for daily operations
2. **Monitor:** Check inventory_history daily
3. **Maintain:** Keep wineries catalog updated
4. **Optimize:** Review and adjust as needed
5. **Document:** Share learnings with team

---

**Migration Guide Version:** 1.0
**Last Updated:** December 31, 2025
**For:** Wine Assistant v1.0.4
**Contact:** Wine Assistant Development Team
