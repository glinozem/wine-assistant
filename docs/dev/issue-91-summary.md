# Issue #91: Add ETL Unit Tests ✅

## Summary

All core ETL scripts now covered with full or near-full unit test coverage:

| File                          | Statements | Missed | Coverage |
|-------------------------------|------------|--------|----------|
| scripts/idempotency.py        | 48         | 0      | 100% ✅   |
| scripts/date_extraction.py    | 83         | 2      | 97.59% ✅ |
| scripts/load_csv.py           | 329        | 56     | ~83% ✅   |

## Highlights

### 🧪 Tests

- 78 total unit tests
- All pass locally with no errors
- CI-compatible schema setup in `tests/fixtures/schema.sql`

### 🧰 Covered Logic

- Duplicate file detection via SHA256 hash
- Envelope and price list creation
- CSV/Excel file loading
- Header canonicalization
- Date extraction from filename, cell, and text
- Discount extraction from Excel
- Structured rollback for all DB tests

### 🧾 Files

- `tests/unit/test_idempotency.py`
- `tests/unit/test_date_extraction.py`
- `tests/unit/test_load_csv.py`
- `tests/fixtures/schema.sql`
- `conftest.py` with rollback DB fixture

## Final Status

- ✅ All tests pass locally
- 🧹 Feature branch deleted after merge
- 🧭 Issue #91 closed
