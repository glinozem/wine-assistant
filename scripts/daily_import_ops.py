#!/usr/bin/env python3
"""
Daily Import Orchestrator v1.2.2.1 HOTFIX

CRITICAL HOTFIXES (staging blockers):
1. ✅ run_id from CLI arg (--run-id) - fixes 404 in /runs
2. ✅ is_relative_to() instead of startswith() - real path traversal protection
3. ✅ Atomic log write (tmp → os.replace)
4. ✅ os.chdir() moved to main() (not module level)

Previous fixes (v1.2.2 FINAL):
- BLOCKER A-D (enrich_producers, move, PROJECT_ROOT, regex)
- RISK 3.1-3.2 (lock constant, dotenv)
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

# ==================== PROJECT SETUP ====================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# HOTFIX 4: os.chdir moved to main() (not module level)

# Constants
UTC = timezone.utc
INBOX_DIR = PROJECT_ROOT / "data" / "inbox"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"
QUARANTINE_DIR = PROJECT_ROOT / "data" / "quarantine"
LOG_DIR = PROJECT_ROOT / "data" / "logs" / "daily-import"

ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

ADVISORY_LOCK_ID = 999999001

# Enums
class SkipReason(str, Enum):
    ALREADY_IMPORTED_SAME_HASH = "ALREADY_IMPORTED_SAME_HASH"
    ALREADY_IMPORTED_SAME_EFFECTIVE_DATE = "ALREADY_IMPORTED_SAME_EFFECTIVE_DATE"
    NO_FILES_IN_INBOX = "NO_FILES_IN_INBOX"
    INVALID_EXTENSION = "INVALID_EXTENSION"
    OTHER = "OTHER"

class SelectedMode(str, Enum):
    AUTO_INBOX_NEWEST = "AUTO_INBOX_NEWEST"
    MANUAL_LIST = "MANUAL_LIST"

class RunStatus(str, Enum):
    OK = "OK"
    OK_WITH_SKIPS = "OK_WITH_SKIPS"
    FAILED = "FAILED"

class LockAcquireError(Exception):
    pass

# ==================== Path Traversal Protection (HOTFIX 2) ====================
def validate_inbox_file(filename: str) -> Path:
    # 1) normalize Windows path separators
    raw = (filename or "").strip().strip('"').strip("'").replace("\\", "/")
    if not raw:
        raise ValueError("Empty filename")

    p = Path(raw)

    # 2) Build candidate path
    if p.is_absolute():
        file_path = p.resolve()
    else:
        # If user passed only basename -> treat as inbox file
        if len(p.parts) == 1:
            file_path = (INBOX_DIR / p.name).resolve()
        else:
            # treat as path relative to PROJECT_ROOT (e.g. data/inbox/xxx.xlsx)
            file_path = (PROJECT_ROOT / p).resolve()

    # 3) extension check
    if file_path.suffix.lower() != ".xlsx":
        raise ValueError(f"Invalid extension: {file_path.name}")

    inbox_resolved = INBOX_DIR.resolve()

    # 4) traversal protection
    try:
        if not file_path.is_relative_to(inbox_resolved):
            raise ValueError(f"Path traversal blocked: {filename}")
    except AttributeError:
        try:
            common = os.path.commonpath([str(inbox_resolved), str(file_path)])
        except ValueError:
            raise ValueError(f"Path traversal blocked: {filename}")

        if common != str(inbox_resolved):
            raise ValueError(f"Path traversal blocked: {filename}")

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path.name}")

    return file_path


def coalesce_xlsx_args(parts: List[str]) -> List[str]:
    """
    Склеивает argv-токены в имена файлов, которые заканчиваются на .xlsx.
    Позволяет работать с 'неправильно' процитированными путями/именами
    (например, когда имя с пробелами распалось на несколько аргументов).
    """
    out: List[str] = []
    buf: List[str] = []

    for part in parts or []:
        if part is None:
            continue
        s = str(part).strip()
        if not s:
            continue

        buf.append(s)
        if s.lower().endswith(".xlsx"):
            out.append(" ".join(buf))
            buf = []

    if buf:
        # Остались токены без завершающего .xlsx — это почти всегда ошибка квотинга
        out.append(" ".join(buf))

    return out


def parse_effective_date_from_filename(name: str) -> Optional[str]:
    """
    Extracts effective date from filename. Supports:
      - YYYY_MM_DD
      - YYYY-MM-DD
      - YYYY.MM.DD
      - YYYYMMDD
    Returns ISO date string YYYY-MM-DD or None.
    """
    if not name:
        return None

    # 1) With separators
    m = re.search(
        r'(?<!\d)(20\d{2})[._-](0[1-9]|1[0-2])[._-](0[1-9]|[12]\d|3[01])(?!\d)',
        name
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(y, mo, d)  # validate calendar date
        except ValueError:
            return None
        return f"{y:04d}-{mo:02d}-{d:02d}"

    # 2) Without separators: YYYYMMDD
    m2 = re.search(
        r'(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)',
        name
    )
    if not m2:
        return None

    y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    try:
        datetime(y, mo, d)  # validate calendar date
    except ValueError:
        return None

    return f"{y:04d}-{mo:02d}-{d:02d}"


# ==================== Database ====================
def get_db_connection():
    try:
        return psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"]
        )
    except KeyError as e:
        raise RuntimeError(f"Missing env var: {e}")

def try_acquire_lock(conn) -> bool:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
        acquired = cursor.fetchone()[0]
        cursor.close()
        if not acquired:
            raise LockAcquireError(f"Lock {ADVISORY_LOCK_ID} held")
        return True
    except psycopg2.Error as e:
        raise LockAcquireError(f"DB error: {e}")

def release_lock(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
        cursor.close()
    except Exception:
        pass

def try_mark_inbox_upload_moved(
    conn,
    *,
    sha256: str,
    saved_name: str,
    new_status: str,
    moved_path: str,
    run_id: str,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Best-effort: если файл был загружен через API и зарегистрирован в public.ops_daily_import_uploads,
    помечаем, что он перемещён из INBOX (ARCHIVED/QUARANTINED) и доклеиваем метаданные.

    Важно:
    - Это NO-OP, если строки нет (файл попал в INBOX вручную).
    - Не должно валить импорт при любой DB-ошибке (миграция не применена, таблицы нет и т.п.).
    """
    if conn is None:
        return
    if new_status not in {"ARCHIVED", "QUARANTINED"}:
        return

    meta: Dict[str, Any] = {"run_id": run_id, "moved_to": moved_path}
    if extra_meta:
        for k, v in extra_meta.items():
            if v is not None:
                meta[k] = v

    payload = json.dumps(meta, ensure_ascii=False)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.ops_daily_import_uploads
                SET status   = %s,
                    moved_at = now(),
                    metadata = coalesce(metadata, '{}'::jsonb) || %s::jsonb
                WHERE status = 'INBOX'
                  AND sha256 = %s
                  AND saved_name = %s
                """,
                (
                    new_status,
                    payload,
                    sha256,
                    saved_name,
                ),
            )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        # Best-effort: не мешаем импорту. Лог в stderr.
        try:
            print(
                f"[WARN] ops_daily_import_uploads update failed: saved_name={saved_name} sha256={sha256[:12]}...",
                file=sys.stderr,
            )
        except Exception:
            pass


# ==================== File Operations ====================
def compute_file_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def archive_file(file_path: Path) -> str:
    import shutil
    now = datetime.now(UTC)
    month_dir = ARCHIVE_DIR / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now.strftime("%Y%m%d-%H%M%S")
    archive_path = month_dir / f"{timestamp}_{file_path.name}"

    shutil.move(str(file_path), str(archive_path))

    try:
        rel_path = archive_path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel_path = archive_path
    return str(rel_path)

def quarantine_file(file_path: Path, file_name: str) -> str:
    import shutil
    now = datetime.now(UTC)
    quar_month = QUARANTINE_DIR / now.strftime("%Y-%m")
    quar_month.mkdir(parents=True, exist_ok=True)
    quar_path = quar_month / f"{now.strftime('%Y%m%d-%H%M%S')}_{file_name}"

    shutil.move(str(file_path), str(quar_path))

    try:
        rel_path = quar_path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel_path = quar_path
    return str(rel_path)

# ==================== Process File ====================
def process_file(
    file_path: Path,
    selected_mode: SelectedMode,
    run_id: str,
    conn: Any,
) -> Dict[str, Any]:
    started_at = datetime.now(UTC)
    file_name = file_path.name
    guessed_effective_date = parse_effective_date_from_filename(file_name)

    result = {
        "original_name": file_name,
        "original_path": str(file_path),
        "selected_mode": selected_mode.value,
        "status": None,
        "skip_reason": None,
        "effective_date": guessed_effective_date,
        "envelope_id": None,
        "rows_good": 0,
        "rows_quarantine": 0,
        "sha256": None,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "duration_ms": None,
        "archive_path": None,
        "quarantine_path": None,
        "error": None
    }

    try:
        file_hash = compute_file_hash(file_path)
        result["sha256"] = file_hash

        cmd = [sys.executable, "-m", "scripts.load_csv", "--excel", str(file_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        stdout_output = proc.stdout
        stderr_output = proc.stderr
        combined_output = "\n".join([stdout_output or "", stderr_output or ""])

        if re.search(r'\bSKIP\b.*\balready imported\b', combined_output,
                     re.IGNORECASE):
            result["status"] = "SKIPPED"
            result["skip_reason"] = SkipReason.ALREADY_IMPORTED_SAME_HASH.value
            result["archive_path"] = archive_file(file_path)

            try_mark_inbox_upload_moved(
                conn,
                sha256=file_hash,
                saved_name=file_name,
                new_status="ARCHIVED",
                moved_path=result["archive_path"],
                run_id=run_id,
                extra_meta={
                    "import_status": result["status"],
                    "skip_reason": result["skip_reason"],
                    "mode": selected_mode.value,
                },
            )

        elif proc.returncode == 0:
            result["status"] = "IMPORTED"

            for line in combined_output.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                line_lower = line_stripped.lower()

                # Envelope id: prefer UUID match
                m_env = re.search(
                    r'\benvelope(?:\s*(?:id|_id))?\s*:\s*([0-9a-fA-F-]{36})\b',
                    line_stripped, re.IGNORECASE)
                if m_env:
                    result["envelope_id"] = m_env.group(1)
                    continue

                # Effective date (YYYY-MM-DD)
                if "effective date" in line_lower or "effective_date" in line_lower:
                    m_date = re.search(r'(\d{4}-\d{2}-\d{2})', line_stripped)
                    if m_date and not result.get("effective_date"):
                        result["effective_date"] = m_date.group(1)
                    else:
                        pass
                    continue

                # rows good: handles "Rows processed (good): 123", "Rows good: 123", "Rows inserted: 123"
                m_good = re.search(
                    r'rows\s*(?:processed\s*\(good\)|good|inserted)\s*:\s*(\d+)\b',
                    line_stripped, re.IGNORECASE)
                if m_good:
                    result["rows_good"] = int(m_good.group(1))
                    continue

                # rows quarantine: handles "Rows failed (quarantine): 12", "Rows quarantine: 12", "Rows failed: 12"
                m_quar = re.search(
                    r'rows\s*(?:failed\s*\(quarantine\)|quarantine|failed)\s*:\s*(\d+)\b',
                    line_stripped, re.IGNORECASE)
                if m_quar:
                    result["rows_quarantine"] = int(m_quar.group(1))
                    continue

            result["archive_path"] = archive_file(file_path)

            try_mark_inbox_upload_moved(
                conn,
                sha256=file_hash,
                saved_name=file_name,
                new_status="ARCHIVED",
                moved_path=result["archive_path"],
                run_id=run_id,
                extra_meta={
                    "import_status": result["status"],
                    "mode": selected_mode.value,
                    "envelope_id": result.get("envelope_id"),
                    "effective_date": result.get("effective_date"),
                    "rows_good": result.get("rows_good"),
                    "rows_quarantine": result.get("rows_quarantine"),
                    "etl_exit_code": 0,
                },
            )

        else:
            if proc.returncode == 2:
                result["status"] = "QUARANTINED"
            elif re.search(r'(validationerror|quarantine:|invalid rows)', combined_output, re.IGNORECASE):
                result["status"] = "QUARANTINED"
            else:
                result["status"] = "ERROR"

            result["error"] = (combined_output or "").strip()[:500] or None

            if result["status"] == "QUARANTINED":
                result["quarantine_path"] = quarantine_file(file_path, file_name)

                try_mark_inbox_upload_moved(
                    conn,
                    sha256=file_hash,
                    saved_name=file_name,
                    new_status="QUARANTINED",
                    moved_path=result["quarantine_path"],
                    run_id=run_id,
                    extra_meta={
                        "status": result["status"],
                        "mode": selected_mode.value,
                        "etl_exit_code": int(proc.returncode),
                        "error": result.get("error"),
                    },
                )

    except subprocess.TimeoutExpired:
        result["status"] = "ERROR"
        result["error"] = "Import timeout (>10 minutes)"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)[:500]

    finished_at = datetime.now(UTC)
    result["finished_at"] = finished_at.isoformat()
    result["duration_ms"] = int((finished_at - started_at).total_seconds() * 1000)
    return result

# ==================== Post-steps ====================
def run_post_steps() -> Optional[Dict[str, Any]]:
    result = {
        "wineries_created": 0,
        "products_enriched": 0,
        "inventory_snapshot": {"status": "SKIPPED", "as_of": None}
    }

    try:
        try:
            enrich_cmd = [sys.executable, "-m", "scripts.enrich_producers"]
            proc_enrich = subprocess.run(enrich_cmd, capture_output=True, text=True, timeout=300)

            if proc_enrich.returncode == 0:
                for line in proc_enrich.stdout.split('\n'):
                    if "producers enriched:" in line.lower():
                        match = re.search(r'(\d+)', line)
                        if match:
                            result["products_enriched"] = int(match.group(1))
            else:
                result["enrich_notes"] = f"Enrich failed: {proc_enrich.stderr[:200]}"

        except FileNotFoundError:
            result["enrich_notes"] = "enrich_producers not found (skipped)"

        try:
            snapshot_cmd = [sys.executable, "-m", "scripts.sync_inventory_history"]
            proc_snapshot = subprocess.run(snapshot_cmd, capture_output=True, text=True, timeout=300)

            if proc_snapshot.returncode == 0:
                result["inventory_snapshot"]["status"] = "DONE"
                result["inventory_snapshot"]["as_of"] = datetime.now(UTC).isoformat()
            else:
                result["inventory_snapshot"]["status"] = "FAILED"
                result["inventory_snapshot"]["error"] = proc_snapshot.stderr[:200]

        except FileNotFoundError:
            result["inventory_snapshot"]["status"] = "SKIPPED"
            result["inventory_snapshot"]["notes"] = "sync_inventory_history not found"

    except Exception as e:
        result["inventory_snapshot"]["status"] = "FAILED"
        result["inventory_snapshot"]["error"] = str(e)[:200]

    return result

# ==================== HOTFIX 3: Atomic Log Write ====================
def write_log_atomic(run_id: str, data: dict):
    """
    HOTFIX 3: Atomic log write (tmp → os.replace)
    Same as API - prevents malformed logs
    """
    log_file = LOG_DIR / f"{run_id}.json"
    tmp_file = LOG_DIR / f"{run_id}.json.tmp"

    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        os.replace(str(tmp_file), str(log_file))
    except Exception as e:
        print(f"Error writing log: {e}", file=sys.stderr)
        if tmp_file.exists():
            tmp_file.unlink()

# ==================== Main ====================
def main():
    # HOTFIX 4: os.chdir here (not module level)
    os.chdir(PROJECT_ROOT)

    # HOTFIX 1: Accept --run-id from CLI
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "files"], required=True)
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--run-id", type=str, default=None, help="Use specific run_id (for API)")
    parser.add_argument("--no-log-file", action="store_true", help="Don't write log file (API manages logs)")
    args = parser.parse_args()

    # HOTFIX 1: Use provided run_id or generate new one
    run_id = args.run_id if args.run_id else str(uuid.uuid4())
    started_at = datetime.now(UTC)

    def error_response(error_msg: str, status=RunStatus.FAILED) -> str:
        return json.dumps({
            "run_id": run_id,
            "selected_mode": None,
            "status": status.value,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_ms": int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            "files": [],
            "summary": {
                "files_total": 0,
                "files_imported": 0,
                "files_skipped": 0,
                "files_quarantined": 0,
                "files_failed": 0,
                "rows_good_total": 0,
                "rows_quarantine_total": 0,
                "inventory_snapshot": None,
                "notes": error_msg
            }
        }, indent=2)

    if args.mode == "files" and not args.files:
        print(error_response("mode=files requires --files ..."), flush=True)
        return 0

    if args.mode == "files":
        args.files = coalesce_xlsx_args(args.files)
        bad = [x for x in args.files if not str(x).lower().endswith(".xlsx")]
        if bad:
            print(error_response(
                "Invalid --files arguments (filename likely split by shell quoting). "
                f"Bad entries: {bad}"
            ), flush=True)
            return 0

    conn = None
    try:
        selected_mode = SelectedMode.AUTO_INBOX_NEWEST if args.mode == "auto" else SelectedMode.MANUAL_LIST

        conn = get_db_connection()
        try:
            try_acquire_lock(conn)
        except LockAcquireError as e:
            print(error_response(str(e)), flush=True)
            return 0

        files_to_process = []

        if selected_mode == SelectedMode.AUTO_INBOX_NEWEST:
            xlsx_files = list(INBOX_DIR.glob("*.xlsx"))
            if not xlsx_files:
                skip_result = {
                    "original_name": None,
                    "status": "SKIPPED",
                    "skip_reason": SkipReason.NO_FILES_IN_INBOX.value,
                    "selected_mode": selected_mode.value,
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat()
                }

                finished_at = datetime.now(UTC)
                result = {
                    "run_id": run_id,
                    "selected_mode": selected_mode.value,
                    "status": RunStatus.OK_WITH_SKIPS.value,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
                    "files": [skip_result],
                    "summary": {
                        "files_total": 1,
                        "files_imported": 0,
                        "files_skipped": 1,
                        "files_quarantined": 0,
                        "files_failed": 0,
                        "rows_good_total": 0,
                        "rows_quarantine_total": 0,
                        "inventory_snapshot": None,
                        "notes": "No files in inbox"
                    }
                }

                if not args.no_log_file:
                    write_log_atomic(run_id, result)

                print(json.dumps(result, indent=2), flush=True)
                return 0

            newest = max(xlsx_files, key=lambda p: p.stat().st_mtime)
            files_to_process = [newest]

        else:
            for fname in args.files:
                try:
                    validated_path = validate_inbox_file(fname)
                    files_to_process.append(validated_path)
                except (ValueError, FileNotFoundError) as e:
                    files_to_process.append({
                        "error": True,
                        "filename": fname,
                        "message": str(e)
                    })

        all_results = []
        for file_item in files_to_process:
            if isinstance(file_item, dict) and file_item.get("error"):
                all_results.append({
                    "original_name": file_item["filename"],
                    "effective_date": parse_effective_date_from_filename(
                        file_item["filename"]),
                    "status": "ERROR",
                    "error": file_item["message"],
                    "selected_mode": selected_mode.value,
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(UTC).isoformat()
                })
            else:
                file_result = process_file(file_item, selected_mode, run_id, conn)
                all_results.append(file_result)

        post_steps_result = None
        if any(f["status"] == "IMPORTED" for f in all_results):
            post_steps_result = run_post_steps()

        files_total = len(all_results)
        files_imported = sum(1 for f in all_results if f["status"] == "IMPORTED")
        files_skipped = sum(1 for f in all_results if f["status"] == "SKIPPED")
        files_quarantined = sum(1 for f in all_results if f["status"] == "QUARANTINED")
        files_failed = sum(1 for f in all_results if f["status"] == "ERROR")
        rows_good_total = sum(f.get("rows_good", 0) for f in all_results)
        rows_quarantine_total = sum(f.get("rows_quarantine", 0) for f in all_results)

        if files_failed > 0:
            run_status = RunStatus.FAILED
        elif files_quarantined > 0 or files_skipped > 0:
            run_status = RunStatus.OK_WITH_SKIPS
        else:
            run_status = RunStatus.OK

        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        final_result = {
            "run_id": run_id,
            "selected_mode": selected_mode.value,
            "status": run_status.value,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "files": all_results,
            "summary": {
                "files_total": files_total,
                "files_imported": files_imported,
                "files_skipped": files_skipped,
                "files_quarantined": files_quarantined,
                "files_failed": files_failed,
                "rows_good_total": rows_good_total,
                "rows_quarantine_total": rows_quarantine_total,
                "inventory_snapshot": post_steps_result["inventory_snapshot"] if post_steps_result else None,
                "notes": None
            }
        }

        # HOTFIX 1: Only write log if not --no-log-file
        if not args.no_log_file:
            write_log_atomic(run_id, final_result)

        print(json.dumps(final_result, indent=2), flush=True)
        return 0

    except Exception as e:
        print(error_response(f"Unexpected: {str(e)}"), flush=True)
        return 0

    finally:
        if conn:
            release_lock(conn)
            conn.close()

if __name__ == "__main__":
    sys.exit(main())
