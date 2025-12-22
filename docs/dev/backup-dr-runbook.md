# Backups to MinIO and DR smoke testing

This project includes a local, self-contained backup/restore workflow for PostgreSQL and a DR (disaster recovery) smoke test that validates end-to-end restore from MinIO.

## Components and ports

- API: `http://localhost:18000`
  - Readiness: `GET /ready`
  - Liveness: `GET /health`
- MinIO console/health proxy (as configured by compose): `http://localhost:19000`
  - Liveness: `GET /minio/health/live`
- MinIO internal endpoint (Docker network): `http://minio:9000`
  Used by the `mc` container (MinIO Client).

## Prerequisites

- Docker + Docker Compose
- GNU Make (e.g., via Chocolatey on Windows)
- PowerShell 5.1+ (for `scripts/dr_smoke.ps1`)
- A working `.env` / environment variables expected by the project (API key, etc., if applicable)

## Backup and restore: Make targets

### Start storage (MinIO)

```powershell
make storage-up
```

### Create a backup and upload to MinIO

```powershell
# Creates ./backups/wine_db_YYYYMMDD_HHMMSS.dump
# Uploads to MinIO (bucket/prefix configured in Makefile)
# Prunes local and remote backups to keep BACKUP_KEEP latest
make backup BACKUP_KEEP=2
```

### List remote backups (MinIO)

```powershell
make backups-list-remote
```

### Restore from the remote latest backup

```powershell
# Downloads latest from MinIO into ./restore_tmp/remote_latest.dump
# Drops and recreates wine_db, restores with pg_restore
make restore-remote-latest
```

## DR smoke tests

The DR smoke test validates:

1) backup + upload to MinIO
2) “disaster” simulation
3) restore from MinIO latest
4) post-restore data checks

### Mode: truncate (fast)

Simulates data loss by truncating core tables (local development only).

```powershell
make dr-smoke-truncate DR_BACKUP_KEEP=2
```

### Mode: dropvolume (stronger)

Simulates loss of the DB volume by removing the Postgres volume and recreating the stack.

```powershell
make dr-smoke-dropvolume DR_BACKUP_KEEP=2
```

## How it works (high-level)

- Backup uses `pg_dump -Fc` (custom format) inside the `db` container and copies the dump into `./backups/`.
- Upload/download uses `mc` (MinIO Client) executed in a dedicated `mc` service container from `docker-compose.storage.yml`.
- Restore performs:
  - stop API
  - `dropdb` / `createdb`
  - `pg_restore --clean --if-exists`
  - start API

## Troubleshooting

### `python scripts/sync_inventory_history.py` fails with `could not translate host name "db"`

That script expects Docker-internal DNS names (`db`). Run it inside the API container via the Make target:

```powershell
make sync-inventory-history-dry-run
make sync-inventory-history
```

### Orphan containers warning

You may see:

- “Found orphan containers …”

It is typically harmless, but if you renamed/removed services, clean up:

```powershell
docker compose down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.storage.yml down --remove-orphans
```

### MinIO `mc` credential warning

`mc` may print a warning about updating credentials. For local development, the configured access/secret in compose is expected. For production, use secrets (do not commit credentials).

## Safety

- `dr-smoke-truncate` and `dr-smoke-dropvolume` are intended for **local environments only**.
- Do not run destructive operations against shared or production databases.

## Backup/DR observability (optional)

If you run the observability stack (`docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d`),
backup/DR workflows emit structured JSONL events into:

- `logs/backup-dr/events.jsonl`

Promtail is configured to scrape this file (mounted into the `promtail` container) and push events to Loki.
Grafana will auto-provision the dashboard:

- **Wine Assistant — Backup & DR** (`observability/grafana/dashboards/wine-assistant-backup-dr.json`)

Typical signals:
- Backups completed (24h)
- Age since last local backup (seconds)
- Restore operations completed (7d)
- Remote pruned backups (deleted_count sum, 7d)
