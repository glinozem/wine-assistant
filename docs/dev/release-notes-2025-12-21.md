# Release notes — 2025-12-21

## Operations / Reliability

- Added MinIO-based backup/restore workflow for the local PostgreSQL database:
  - Local dumps in `./backups/` (custom format, `pg_dump -Fc`)
  - Remote storage in MinIO (via `mc` container)
  - Automatic pruning of local and remote dumps (`BACKUP_KEEP=N`)
- Added DR smoke test (`scripts/dr_smoke.ps1`) to validate end-to-end restore from MinIO:
  - `truncate` mode: truncates core tables and restores
  - `dropvolume` mode: recreates DB volume and restores
- Added documentation runbook for backup/restore and DR smoke testing.

## Notes

- DR smoke tests are intended for local development only (destructive).
