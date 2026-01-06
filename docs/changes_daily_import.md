# Ops Daily Import v1.2.2.2: Implementation & Changes

## Overview

Daily Import is an operational pipeline for ingesting supplier Excel price lists (`.xlsx`) placed into `data/inbox/`, processing them through the ETL layer, and persisting results into the database. Each import run produces a JSON run log (`data/logs/daily-import/<run_id>.json`), and each processed file is moved out of the inbox into either:

- `data/archive/<YYYY-MM>/...` for **IMPORTED** and **SKIPPED**
- `data/quarantine/<YYYY-MM>/...` for **QUARANTINED**
- (typically) remains in inbox only if the run ends in **ERROR** for that file

The implementation is designed to be usable from:
1) **Web UI** (`/daily-import`)
2) **CLI inside container** (`python -m scripts.daily_import_ops ...`)
3) **Windows-friendly PowerShell wrapper** (`scripts/run_daily_import.ps1`)
4) **Makefile targets** (wrapping either CLI or PowerShell)

## Version: v1.2.2.2 (Ops UI + API, Windows-friendly)

This version supersedes the legacy v1.0.4 documentation that referenced `scripts/daily_import.py`. The current “source of truth” entrypoints are:

- `scripts/daily_import_ops.py` (orchestrator)
- `api/ops_daily_import.py` (Ops endpoints registration)
- `api/templates/daily_import.html` (Daily Import web UI)

## Goal

- Provide a predictable, operator-friendly workflow for importing `.xlsx` price lists.
- Ensure correct handling of **spaces** and **Cyrillic** in filenames across Windows + Docker.
- Provide traceability (run logs) and operator actions (download archive/quarantine artifacts).

## What was Added / Changed

### 1) UTF-8 / Unicode hardening (Windows + Docker)

To eliminate Unicode/encoding issues when processing Cyrillic filenames and payloads, the runtime environment is forced to UTF-8:

- `Dockerfile`: `LANG`, `LC_ALL`, `PYTHONUTF8`, `PYTHONIOENCODING`
- `docker-compose.yml`: same environment variables for the `api` container

This ensures consistent behavior for Python, shell tooling, and JSON logs.

### 2) Ops API endpoints (backend)

New protected endpoints (require `X-API-Key`) under:

- `GET  /api/v1/ops/daily-import/inbox`
  - Returns inbox files list with metadata (name/mtime/size) and a boolean `is_latest`.

- `POST /api/v1/ops/daily-import/run`
  - Starts a run. Payload:
    - `{ "mode": "auto" }` — process newest file from inbox
    - `{ "mode": "files", "files": ["<exact file name>", ...] }` — process explicit list

- `GET  /api/v1/ops/daily-import/runs/<run_id>`
  - Returns run status and per-file results (including `archive_path`, `quarantine_path`, `skip_reason`, `rows_good`, `rows_quarantine`, etc.).

Additionally, the UI uses download endpoints for artifacts:

- `GET /api/v1/ops/files/archive/<relpath>`
- `GET /api/v1/ops/files/quarantine/<relpath>`

### 3) Web UI: `api/templates/daily_import.html`

A new operator UI is available at:

- `GET /daily-import`

Key behaviors:
- API key is entered once and stored in `localStorage` (client-side only).
- **Auto** mode processes the newest inbox file.
- **Manual** mode allows selecting files (checkbox list).
- After completion:
  - Shows a clear summary (run_id, selected_mode, status, duration).
  - Shows per-file table including skip reasons and actions to download archive/quarantine artifacts.
  - Detects stale selections (files that are no longer in inbox) and removes them from selection to avoid “File not found”.

Additional UX improvements (requested/implemented):
- After successful processing: toast “Файл обработан и перемещён в archive”.
- If inbox becomes empty after refresh: left panel shows “Inbox пуст (последний файл перемещён в archive)”.
- After successful **MANUAL_LIST** completion: selected files are cleared.
- If a run completes with `files_imported = 0` and `files_skipped > 0`: toast “Новых данных нет: всё уже импортировано”.

### 4) Orchestrator: `scripts/daily_import_ops.py`

The orchestrator is the canonical CLI entrypoint for daily import operations. It is expected to output a JSON object describing the run (including `run_id`, `status`, `summary`, `files[]`).

Supported modes:
- `--mode auto`
- `--mode files --files "<file1>" "<file2>" ...`

Important:
- For **files mode**, filenames must match *exactly* what is returned by `/inbox` (including spaces/case).

### 5) Windows PowerShell wrapper: `scripts/run_daily_import.ps1`

The PowerShell wrapper provides a Windows-friendly experience and avoids quoting pitfalls when filenames contain spaces/Cyrillic.

It executes orchestrator inside the `api` container via `docker-compose exec -T ...` and:
- Parses JSON from stdout/stderr robustly (by scanning for a parseable JSON object).
- Returns meaningful exit codes for CI/automation.

Exit code mapping:
- `0` — OK / OK_WITH_SKIPS (no quarantine)
- `1` — at least one file is QUARANTINED
- `2` — run FAILED or TIMEOUT
- `4` — NO_FILES_IN_INBOX (in auto mode)
- `5` — orchestrator output is not parseable JSON

### 6) Makefile targets (Daily Import section)

The Makefile now provides a dedicated Daily Import section with targets such as:

- `make inbox-ls`
- `make daily-import` (auto via container)
- `make daily-import-files FILES="file1.xlsx file2.xlsx"` (files mode; **not safe** for names with spaces)
- `make daily-import-ps` / `make daily-import-files-ps FILES="a.xlsx,b.xlsx"` (Windows-safe wrapper)
- `make daily-import-history`
- `make daily-import-show RUN_ID=<uuid>`
- `make daily-import-cleanup-archive DAYS=90`
- `make daily-import-quarantine-stats`

## Operational Notes

### Archiving Rules

Per run file result:
- **IMPORTED** → moved to archive
- **SKIPPED** (e.g., `ALREADY_IMPORTED_SAME_HASH`) → moved to archive
- **QUARANTINED** → moved to quarantine (and the error/reason is preserved in run log)
- **ERROR** → the file may remain in inbox (to allow investigation and re-run)

### Run Log Location

Each run creates a JSON file (same schema as API response) in:

- `data/logs/daily-import/<run_id>.json`

Use `make daily-import-history` and `make daily-import-show RUN_ID=...` to inspect.

### Filenames with spaces / Cyrillic (Windows)

Recommendations:
- Prefer **Web UI** for manual selection, or:
- Use **PowerShell wrapper** / Makefile `daily-import-files-ps` target.
- Avoid `make daily-import-files ...` with filenames containing spaces (GNU Make splitting).

## Files Changed / Added

### Added
- `api/ops_daily_import.py`
- `api/templates/daily_import.html`
- `scripts/daily_import_ops.py`

### Modified
- `api/app.py` (route `/daily-import` + ops endpoints registration)
- `Dockerfile` (UTF-8 env)
- `docker-compose.yml` (UTF-8 env for container)
- `Makefile` (Daily Import targets)
- `scripts/run_daily_import.ps1` (new wrapper over orchestrator inside container)

## Testing (smoke)

1) Put a price list into `data/inbox/` (host path, mounted into container).
2) Ensure API is up: `make dev-up`
3) Run one of the workflows:

- UI: open `/daily-import`, set API key, refresh inbox, run import
- CLI:
  - `docker compose exec -T api python -m scripts.daily_import_ops --mode auto`
- PowerShell:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_daily_import.ps1 -Mode auto`

4) Verify:
- `/api/v1/ops/daily-import/inbox` is empty after processing (expected when a single file was processed).
- `data/archive/<YYYY-MM>/...` contains the moved `.xlsx`.
- `data/logs/daily-import/<run_id>.json` exists.

## Migration Notes

- If your docs/scripts reference `scripts/daily_import.py` (legacy), update them to `scripts/daily_import_ops.py`.
- Prefer Makefile `daily-import-ps` / `daily-import-files-ps` on Windows for filenames with spaces.

## Support / Contacts

If you hit an issue, attach:
- `data/logs/daily-import/<run_id>.json`
- container logs: `docker compose logs --tail=200 api`
