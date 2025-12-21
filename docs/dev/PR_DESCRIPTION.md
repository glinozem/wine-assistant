## Summary

This PR adds a local backup/restore workflow for PostgreSQL with remote storage in MinIO, plus an end-to-end DR smoke test that validates restoring the database from MinIO.

## Key changes

- MinIO client tooling (`mc`) wired into the project’s compose profile for backups.
- Make targets for:
  - starting MinIO
  - creating/pruning backups
  - listing remote backups
  - restoring the latest remote backup
  - running DR smoke tests (truncate and dropvolume modes)
- `scripts/dr_smoke.ps1` DR smoke test:
  - performs backup → disaster simulation → restore → post-restore verification
  - compares pre/post counts for `products`, `product_prices`, `inventory`, plus a data quality gate (`bad_rows`)

## How to test

```powershell
docker compose up -d --build
make storage-up

make dr-smoke-truncate DR_BACKUP_KEEP=2
make dr-smoke-dropvolume DR_BACKUP_KEEP=2
```

## Safety

- DR smoke tests are destructive; intended for local environments only.
