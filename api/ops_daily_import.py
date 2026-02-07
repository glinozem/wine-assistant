"""
Daily Import Ops API v1.2.2.2 FINAL-STABLE

EXPLOITATION RISK FIXES:
✅ R1: Write RUNNING log BEFORE proc.start() (no 404 on first poll!)
✅ R2: proc.kill() on timeout + status="TIMEOUT" (no zombie processes!)
✅ R3: timezone.utc everywhere (consistent aware timestamps)

POLISHING:
✅ P1: run-sync also uses --run-id (consistent history)
✅ P2: status="TIMEOUT" (separate from FAILED)

Previous fixes:
- v1.2.2.1 HOTFIX: run_id consistency, path traversal, sys.executable
- v1.2.2 FINAL: daemon=False, atomic logs, JSONDecodeError protection
- v1.2.1: blockers A-D, risks 3.1-3.2
"""

import base64
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request, send_file

# Paths
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "data" / "logs" / "daily-import"
INBOX_DIR = BASE_DIR / "data" / "inbox"
ARCHIVE_DIR = BASE_DIR / "data" / "archive"
QUARANTINE_DIR = BASE_DIR / "data" / "quarantine"

LOGS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_MODES = {"auto", "files"}
MAX_FILES = 50
# Upload limits (env-overridable)
MAX_UPLOAD_FILE_MB = int(os.getenv("OPS_UPLOAD_MAX_FILE_MB", "50"))
MAX_UPLOAD_TOTAL_MB = int(os.getenv("OPS_UPLOAD_MAX_TOTAL_MB", "200"))

MAX_UPLOAD_FILE_BYTES = MAX_UPLOAD_FILE_MB * 1024 * 1024
MAX_UPLOAD_TOTAL_BYTES = MAX_UPLOAD_TOTAL_MB * 1024 * 1024
# Upload dedupe policy (content-based, SHA-256 within INBOX)
# Values: off | reject | skip | rename
# NOTE: in PR-1, "skip" behaves like "reject" but keeps HTTP 200 and reports DUPLICATE in rejected[].
OPS_UPLOAD_DEDUPE_POLICY = os.getenv("OPS_UPLOAD_DEDUPE_POLICY", "reject").strip().lower()
if OPS_UPLOAD_DEDUPE_POLICY not in {"off", "reject", "skip", "rename"}:
    OPS_UPLOAD_DEDUPE_POLICY = "reject"

SYNC_RUN_TIMEOUT_S = int(os.getenv("OPS_DAILY_IMPORT_SYNC_TIMEOUT_S", "900"))
STDIO_TAIL_CHARS = int(os.getenv("OPS_DAILY_IMPORT_STDIO_TAIL_CHARS", "2000"))

OPS_DB_REGISTRY_DEBUG = os.getenv("OPS_DB_REGISTRY_DEBUG", "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_payload(payload: dict) -> tuple[str, list[str]]:
    """
    Validate and normalize user payload for subprocess execution.
    Key goals:
    - allowlist mode
    - prevent argparse option-injection via filenames starting with '-'
    - prevent path traversal / absolute paths (only basenames)
    - ensure files exist in INBOX_DIR
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    mode = payload.get("mode", "auto")
    if mode not in ALLOWED_MODES:
        raise ValueError(f"Invalid mode: {mode}")

    # If not explicit files-mode, ignore files completely
    if mode != "files":
        return mode, []

    files = payload.get("files", []) or []
    if not isinstance(files, list):
        raise ValueError("files must be a list")
    if len(files) > MAX_FILES:
        raise ValueError(f"Too many files (max {MAX_FILES})")

    safe_files: list[str] = []
    for f in files:
        if not isinstance(f, str):
            raise ValueError("files must contain only strings")

        name = _validate_inbox_xlsx_basename(f)
        candidate = INBOX_DIR / name
        if not candidate.exists():
            raise ValueError(f"File not found in inbox: {name}")

        safe_files.append(name)

    if not safe_files:
        raise ValueError("mode=files requires non-empty files list")

    return mode, safe_files


def _validate_inbox_xlsx_basename(raw: str) -> str:
    """
    Return safe basename (unicode preserved) or raise ValueError.

    Rules:
    - must be str, non-empty
    - basename only (no / or \\), no '..'
    - must not start with '-'
    - must end with .xlsx (case-insensitive)
    """
    if not isinstance(raw, str):
        raise ValueError("files must contain only strings")

    name = raw.strip()
    if not name:
        raise ValueError(f"Invalid filename: {raw}")

    # Block traversal / path separators explicitly (Linux Path.name won't catch backslash)
    if "/" in name or "\\" in name:
        raise ValueError(f"Invalid filename: {raw}")
    if "\x00" in name:
        raise ValueError(f"Invalid filename: {raw}")
    if name.startswith("-"):
        raise ValueError(f"Invalid filename: {raw}")

    # Block explicit parent dir tokens (defense-in-depth)
    if name == ".." or name.startswith("..") or ".." in name:
        raise ValueError(f"Invalid filename: {raw}")

    if not name.lower().endswith(".xlsx"):
        raise ValueError(f"Only .xlsx allowed: {name}")

    # keep unicode as-is
    return name


def register_ops_daily_import(app, require_api_key, db_connect, db_query):
    """Register ops daily-import endpoints"""

    def _list_inbox_files():
        files = []
        if INBOX_DIR.exists():
            xlsx_files = list(INBOX_DIR.glob("*.xlsx"))
            newest_file = max(xlsx_files, key=lambda p: p.stat().st_mtime) if xlsx_files else None

            for file_path in xlsx_files:
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_latest": (file_path == newest_file)
                })
        return files

    def _allocate_non_conflicting_name(dest_dir: Path, desired: str) -> str:
        p = dest_dir / desired
        if not p.exists():
            return desired

        stem = Path(desired).stem
        suffix = Path(desired).suffix  # ".xlsx"
        for i in range(1, 10_000):
            candidate = f"{stem} ({i}){suffix}"
            if not (dest_dir / candidate).exists():
                return candidate
        raise ValueError("Too many name conflicts")

    def _save_upload_atomic(file_storage, dest_dir: Path, saved_name: str,
                            max_bytes: int) -> int:
        dest_dir.mkdir(parents=True, exist_ok=True)

        tmp_path = dest_dir / f".upload-{uuid.uuid4().hex}.tmp"
        final_path = dest_dir / saved_name

        written = 0
        try:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = file_storage.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("FILE_TOO_LARGE")
                    f.write(chunk)

            os.replace(str(tmp_path), str(final_path))
            return written
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    # ==================== SHA-256 / Dedupe helpers (PR-1) ====================

    def _write_upload_tmp_with_sha(file_storage, dest_dir: Path,
                                   max_bytes: int) -> tuple[Path, int, str]:
        """
        Stream upload to tmp file while computing SHA-256.
        Returns (tmp_path, size_bytes, sha256_hex).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_dir / f".upload-{uuid.uuid4().hex}.tmp"
        written = 0
        h = hashlib.sha256()
        try:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = file_storage.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("FILE_TOO_LARGE")
                    h.update(chunk)
                    f.write(chunk)
            return tmp_path, written, h.hexdigest()
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise

    def _finalize_upload_tmp(tmp_path: Path, dest_dir: Path,
                             saved_name: str) -> Path:
        final_path = dest_dir / saved_name
        os.replace(str(tmp_path), str(final_path))
        return final_path

    # ==================== Atomic log writes ====================
    def write_log_atomic(run_id, data):
        """Atomic log write (tmp → os.replace)"""
        log_file = LOGS_DIR / f"{run_id}.json"
        tmp_file = LOGS_DIR / f"{run_id}.json.tmp"

        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
               json.dump(data, f, indent=2, ensure_ascii=False)

            os.replace(str(tmp_file), str(log_file))
        except Exception as e:
            print(f"Error writing log: {e}")
            if tmp_file.exists():
                tmp_file.unlink()

    def _db_exec(conn, sql: str, params: tuple = ()) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def _db_query_write(conn, sql: str, params: tuple = ()) -> list[dict]:
        try:
            rows = db_query(conn, sql, params) or []
            conn.commit()
            return rows
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def _db_get_inbox_upload_by_sha256(conn, sha256: str) -> dict | None:
        rows = db_query(
            conn,
            """
            SELECT upload_id, saved_name, original_name, sha256, size_bytes, uploaded_at
            FROM public.ops_daily_import_uploads
            WHERE status = 'INBOX' AND sha256 = %s
            LIMIT 1
            """,
            (sha256,),
        ) or []
        return rows[0] if rows else None

    def _db_get_ingest_envelope_by_sha256_best_effort(conn, sha256: str) -> dict | None:
        try:
            rows = db_query(
                conn,
                """
                SELECT envelope_id
                FROM public.ingest_envelope
                WHERE file_sha256 = %s
                LIMIT 1
                """,
                (sha256,),
            ) or []
            return rows[0] if rows else None
        except Exception as e:
            # best-effort: если таблица ещё не задеплоена — не блокируем uploads
            msg = str(e).lower()
            if getattr(e, "pgcode", None) == "42p01" or ("ingest_envelope" in msg and "does not exist" in msg):
                return None
            raise

    def _db_try_register_inbox_upload(
        conn,
        *,
        original_name: str,
        saved_name: str,
        sha256: str,
        size_bytes: int,
        metadata: dict | None = None,
    ) -> tuple[bool, dict | None]:
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        rows = _db_query_write(
            conn,
            """
            INSERT INTO public.ops_daily_import_uploads
              (status, original_name, saved_name, sha256, size_bytes, metadata)
            VALUES
              ('INBOX', %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (sha256) WHERE status = 'INBOX'
            DO NOTHING
            RETURNING upload_id
            """,
            (original_name, saved_name, sha256, int(size_bytes), payload),
        )
        if rows:
            return True, rows[0]
        return False, _db_get_inbox_upload_by_sha256(conn, sha256)

    def _is_saved_name_unique_violation(e: Exception) -> bool:
        # psycopg2: UniqueViolation -> pgcode 23505, constraint in e.diag.constraint_name
        if getattr(e, "pgcode", None) != "23505":
            return False

        diag = getattr(e, "diag", None)
        cname = getattr(diag, "constraint_name", None)
        if cname == "ux_ops_di_uploads_inbox_saved_name":
            return True

        # fallback: message sniffing
        s = str(e).lower()
        return (
            "ux_ops_di_uploads_inbox_saved_name" in s
            or ("duplicate key value" in s and "saved_name" in s)
        )

    def _db_conn_or_none():
        conn, err = db_connect()
        if err or conn is None:
            return None
        return conn

    def _dt_ensure_aware(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _dt_to_iso(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, datetime):
            return _dt_ensure_aware(v).isoformat()
        return str(v)

    def _iso_to_dt(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return _dt_ensure_aware(v)
        if isinstance(v, str) and v:
            s = v.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                return None
            return _dt_ensure_aware(dt)
        return None

    def _tail(s: str | None, limit: int) -> str | None:
        if not s:
            return None
        s = s.replace("\x00", "")
        if len(s) <= limit:
            return s
        return s[-limit:]

    def _summary_min(files: list[str]) -> dict:
        return {
            "files_total": len(files or []),
            "files_imported": 0,
            "files_skipped": 0,
            "files_quarantined": 0,
            "files_failed": 0,
        }

    def _calc_duration_ms(started_at: datetime | None,
                          finished_at: datetime) -> int | None:
        if started_at is None:
            return None
        return int((finished_at - started_at).total_seconds() * 1000)

    def _encode_cursor(started_at: datetime, run_id: str) -> str:
        payload = {
            "started_at": _dt_ensure_aware(started_at).isoformat(),
            "run_id": run_id,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(cur: str) -> tuple[datetime, str]:
        s = (cur or "").strip()
        if not s:
            raise ValueError("empty cursor")

        pad = "=" * (-len(s) % 4)
        raw = base64.urlsafe_b64decode((s + pad).encode("ascii"))
        obj = json.loads(raw.decode("utf-8"))

        dt = _iso_to_dt(obj.get("started_at"))
        if dt is None:
            raise ValueError("bad cursor.started_at")

        run_id = str(uuid.UUID(str(obj.get("run_id"))))
        return dt, run_id

    def _summary_legacy_fields(summary: dict) -> dict:
        s = summary or {}
        return {
            "files_total": s.get("files_total", 0),
            "files_imported": s.get("files_imported", 0),
            "files_skipped": s.get("files_skipped", 0),
            "files_quarantined": s.get("files_quarantined", 0),
            "files_failed": s.get("files_failed", 0),
        }

    def _item_from_db_row(row: dict) -> dict:
        summary = row.get("summary") or {}
        return {
            "run_id": str(row.get("run_id")),
            "status": row.get("status"),
            "requested_mode": row.get("requested_mode"),
            "selected_mode": row.get("selected_mode"),
            "started_at": _dt_to_iso(row.get("started_at")),
            "finished_at": _dt_to_iso(row.get("finished_at")),
            "duration_ms": row.get("duration_ms"),
            "summary": summary,
        }

    def _legacy_from_item(item: dict) -> dict:
        summary = item.get("summary") or {}
        out = {
            "run_id": item.get("run_id"),
            "status": item.get("status"),
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "duration_ms": item.get("duration_ms"),
        }
        out.update(_summary_legacy_fields(summary))
        return out

    def _db_registry_insert_start(run_id: str, requested_mode: str, files: list[str], started_at: datetime) -> None:
        conn = _db_conn_or_none()
        if conn is None:
            return
        try:
            summary = {
                "files_total": len(files or []),
                "files_imported": 0,
                "files_skipped": 0,
                "files_quarantined": 0,
                "files_failed": 0,
            }
            sql = """
            INSERT INTO public.ops_daily_import_runs
                  (run_id, requested_mode, status, started_at, summary, log_relpath)
            VALUES
              (%s, %s, 'RUNNING', %s, %s::jsonb, %s)
            ON CONFLICT (run_id) DO UPDATE
            SET
              requested_mode = EXCLUDED.requested_mode,
              status = 'RUNNING',
              started_at = LEAST(public.ops_daily_import_runs.started_at, EXCLUDED.started_at),
              summary = EXCLUDED.summary,
              log_relpath = COALESCE (public.ops_daily_import_runs.log_relpath, EXCLUDED.log_relpath),
              updated_at = now();
                  """
            _db_exec(
                conn,
                sql,
                (run_id, requested_mode, started_at, json.dumps(summary), f"{run_id}.json"),
            )

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _db_registry_update_finish(run_id: str, requested_mode: str, payload: dict) -> None:
        conn = _db_conn_or_none()
        if conn is None:
            return
        try:
            status = payload.get("status") or "FAILED"
            selected_mode = payload.get("selected_mode")
            finished_at = _iso_to_dt(payload.get("finished_at")) or datetime.now(timezone.utc)
            started_at = _iso_to_dt(payload.get("started_at"))
            duration_ms = payload.get("duration_ms")

            if duration_ms is None and started_at is not None:
                duration_ms = int((_dt_ensure_aware(finished_at) - _dt_ensure_aware(started_at)).total_seconds() * 1000)

            summary = payload.get("summary")
            if not isinstance(summary, dict) or not summary:
                summary = {}

            result_json = payload if isinstance(payload, dict) and payload else {}

            sql = """
            INSERT INTO public.ops_daily_import_runs
              (run_id, requested_mode, status, selected_mode, started_at, finished_at, duration_ms, summary, result_json, log_relpath)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (run_id) DO UPDATE
            SET
             requested_mode = EXCLUDED.requested_mode,
             status = EXCLUDED.status,
             selected_mode = COALESCE (EXCLUDED.selected_mode, public.ops_daily_import_runs.selected_mode),
             started_at = LEAST(public.ops_daily_import_runs.started_at, EXCLUDED.started_at),
             finished_at = COALESCE (EXCLUDED.finished_at, public.ops_daily_import_runs.finished_at),
             duration_ms = COALESCE (EXCLUDED.duration_ms, public.ops_daily_import_runs.duration_ms),
             summary = CASE
               WHEN EXCLUDED.summary = '{}'::jsonb THEN public.ops_daily_import_runs.summary
               ELSE EXCLUDED.summary
             END,
             result_json = CASE
               WHEN EXCLUDED.result_json = '{}'::jsonb THEN public.ops_daily_import_runs.result_json
               ELSE EXCLUDED.result_json
             END,
              log_relpath = COALESCE(public.ops_daily_import_runs.log_relpath, EXCLUDED.log_relpath),
              updated_at = now();
            """

            # If payload doesn't carry started_at, fallback to finished_at (best-effort)
            started_at_dt = started_at or finished_at

            _db_exec(
                conn,
                sql,
                (
                    run_id,
                    requested_mode,
                    status,
                    selected_mode,
                    started_at_dt,
                    finished_at,
                    duration_ms,
                    json.dumps(summary),
                    json.dumps(result_json),
                    f"{run_id}.json",
                ),
            )

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def execute_import_background(run_id, mode, files):
        """
        Execute import in background.

        NOTE: RUNNING log already written by POST /run (FIX R1)
        This just executes and updates the log.
        """

        # Build command (pass --run-id, use sys.executable)
        cmd = [
            sys.executable, "-m", "scripts.daily_import_ops",
            "--mode", mode,
            "--run-id", run_id,
            "--no-log-file"
        ]

        if mode == "files":
            cmd.extend(["--files", *files])

        try:
            proc = subprocess.Popen(  # nosemgrep: python.flask.security.injection.subprocess-injection.subprocess-injection
                cmd,
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )

            # FIX R2 + POLISH P2: Catch TimeoutExpired separately
            try:
                stdout, stderr = proc.communicate(timeout=900)

                # Parse result
                try:
                    result = json.loads(stdout)

                    # Verify run_id consistency
                    if result.get("run_id") != run_id:
                        result["run_id"] = run_id

                    write_log_atomic(run_id, result)

                    _db_registry_update_finish(run_id, mode, result)

                except json.JSONDecodeError as e:
                    error_result = {
                        "run_id": run_id,
                        "status": "FAILED",
                        "error": f"Invalid JSON from orchestrator: {e}",
                        "stdout": stdout[:1000] if stdout else "",
                        "stderr": stderr[:1000] if stderr else "",
                        "finished_at": datetime.now(timezone.utc).isoformat()  # FIX R3
                    }

                    write_log_atomic(run_id, error_result)

                    _db_registry_update_finish(run_id, mode, error_result)

            except subprocess.TimeoutExpired:
                # FIX R2: Kill the process and wait for it to die
                proc.kill()
                try:
                    proc.wait(timeout=10)  # Give it 10 seconds to die
                except subprocess.TimeoutExpired:
                    proc.terminate()  # Force kill if still alive
                    proc.wait()

                # POLISH P2: Use status="TIMEOUT" (not FAILED)
                timeout_result = {
                    "run_id": run_id,
                    "status": "TIMEOUT",  # ✅ Separate status!
                    "error": "Import timeout (>15 minutes). Process terminated.",
                    "finished_at": datetime.now(timezone.utc).isoformat()  # FIX R3
                }

                write_log_atomic(run_id, timeout_result)

                _db_registry_update_finish(run_id, mode, timeout_result)

        except Exception as e:
            error_result = {
                "run_id": run_id,
                "status": "FAILED",
                "error": str(e),
                "finished_at": datetime.now(timezone.utc).isoformat()  # FIX R3
            }

            write_log_atomic(run_id, error_result)

            _db_registry_update_finish(run_id, mode, error_result)

    # ==================== ENDPOINTS ====================

    @app.route("/api/v1/ops/daily-import/inbox", methods=["GET"])
    @require_api_key
    def ops_daily_import_inbox():
        """GET /api/v1/ops/daily-import/inbox - list inbox files"""
        return jsonify({"files": _list_inbox_files()}), 200

    @app.route("/api/v1/ops/daily-import/inbox/upload", methods=["POST"])
    @require_api_key
    def ops_daily_import_inbox_upload():
        try:
            # total request size pre-check (best-effort)
            cl = request.content_length
            if cl is not None and cl > MAX_UPLOAD_TOTAL_BYTES:
                return jsonify({"error": "payload_too_large"}), 413

            # accept both field names
            fs_list = []
            fs_list.extend(request.files.getlist("files"))
            fs_list.extend(request.files.getlist("files[]"))

            if not fs_list:
                return jsonify(
                    {"error": "No files provided (field: files)"}), 400
            if len(fs_list) > MAX_FILES:
                return jsonify(
                    {"error": f"Too many files (max {MAX_FILES})"}), 400

            uploaded = []
            rejected = []

            raw_policy = OPS_UPLOAD_DEDUPE_POLICY
            dedupe_policy = raw_policy
            if raw_policy in {"rename", "off"}:
                try:
                    app.logger.warning(
                        "OPS_UPLOAD_DEDUPE_POLICY=%s is not supported with DB-truth dedupe (unique sha256 in INBOX). "
                        "Treating as 'reject'.",
                        raw_policy,
                    )
                except Exception:
                    pass
                dedupe_policy = "reject"

            conn, err = db_connect()
            if err or conn is None:
                return jsonify({"error": "db_unavailable", "message": err or "db_connect failed"}), 503

            total_written = 0
            try:
                for fs in fs_list:
                    original = getattr(fs, "filename", None) or ""
                    try:
                        safe_name = _validate_inbox_xlsx_basename(original)

                        tmp_path, size, sha256 = _write_upload_tmp_with_sha(
                            fs, INBOX_DIR, MAX_UPLOAD_FILE_BYTES
                        )

                        if total_written + size > MAX_UPLOAD_TOTAL_BYTES:
                            try:
                                tmp_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            rejected.append({
                                "original_name": original,
                                "reason": "TOTAL_TOO_LARGE",
                                "message": f"Total upload limit exceeded ({MAX_UPLOAD_TOTAL_MB} MB)",
                                "sha256": sha256,
                            })
                            continue

                        env = _db_get_ingest_envelope_by_sha256_best_effort(conn, sha256)
                        if env:
                            try:
                                tmp_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            rejected.append({
                                "original_name": original,
                                "reason": "ALREADY_IMPORTED_SAME_HASH",
                                "envelope_id": str(env.get("envelope_id")) if env.get("envelope_id") else None,
                                "message": "File already imported (SHA-256 exists in ingest_envelope)",
                                "sha256": sha256,
                            })
                            continue

                        # retry loop for saved_name unique collisions
                        ok = False
                        info = None
                        saved_name = None

                        stem = Path(safe_name).stem
                        suffix = Path(safe_name).suffix

                        for attempt in range(5):
                            name_hint = safe_name if attempt == 0 else f"{stem} ({attempt}){suffix}"
                            candidate = _allocate_non_conflicting_name(INBOX_DIR, name_hint)
                            try:
                                ok, info = _db_try_register_inbox_upload(
                                    conn,
                                    original_name=original,
                                    saved_name=candidate,
                                    sha256=sha256,
                                    size_bytes=size,
                                    metadata={"dedupe_policy": dedupe_policy},
                                )
                                saved_name = candidate
                                break
                            except Exception as e:
                                if _is_saved_name_unique_violation(e):
                                    continue
                                raise

                        if saved_name is None:
                            # Не смогли подобрать имя (DB unique по saved_name) — это НЕ DUPLICATE по контенту.
                            try:
                                tmp_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            rejected.append({
                                "original_name": original,
                                "reason": "NAME_CONFLICT",
                                "message": "Could not allocate unique saved_name in DB (INBOX)",
                                "sha256": sha256,
                            })
                            continue

                        if not ok:
                            try:
                                tmp_path.unlink(missing_ok=True)
                            except Exception:
                                pass

                            dup_saved = (info or {}).get("saved_name")
                            dup_id = (info or {}).get("upload_id")
                            rejected.append({
                                "original_name": original,
                                "reason": "DUPLICATE",
                                "duplicate_upload_id": dup_id,
                                "message": f"Duplicate content (SHA-256) in inbox; policy={dedupe_policy}",
                                "sha256": sha256,
                                "duplicate_of": [dup_saved] if dup_saved else [],
                            })
                            continue

                        try:
                            _finalize_upload_tmp(tmp_path, INBOX_DIR, saved_name)
                        except Exception:
                            # avoid INBOX ghost in DB
                            try:
                                _db_query_write(
                                    conn,
                                    """
                                    UPDATE public.ops_daily_import_uploads
                                    SET status='DELETED',
                                        moved_at=now()
                                    WHERE status = 'INBOX'
                                      AND sha256 = %s
                                    """,
                                    (sha256,),
                                )
                            except Exception:
                                pass
                            raise

                        total_written += size
                        uploaded.append({
                            "original_name": original,
                            "saved_name": saved_name,
                            "size": size,
                            "sha256": sha256,
                            "status": "UPLOADED",
                            "upload_id": (info or {}).get("upload_id"),
                        })

                        try:
                            app.logger.info(
                                "ops daily-import upload(db): original=%s saved=%s size=%s sha256=%s upload_id=%s",
                                original, saved_name, size, sha256,
                                (info or {}).get("upload_id"),
                            )
                        except Exception:
                            pass

                    except ValueError as e:
                        reason = str(e)
                        if reason == "FILE_TOO_LARGE":
                            rejected.append({
                                "original_name": original,
                                "reason": "FILE_TOO_LARGE",
                                "message": f"Max per-file size is {MAX_UPLOAD_FILE_MB} MB",
                            })
                        else:
                            rejected.append({
                                "original_name": original,
                                "reason": "INVALID_FILE",
                                "message": str(e),
                            })
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            return jsonify({
                "uploaded": uploaded,
                "rejected": rejected,
                "inbox": {"files": _list_inbox_files()},
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.route("/api/v1/ops/daily-import/run", methods=["POST"])
    @require_api_key
    def ops_daily_import_run():
        """
        POST /api/v1/ops/daily-import/run - ASYNC import (RECOMMENDED)

        FIX R1: Write RUNNING log BEFORE proc.start() (no 404 on first poll!)
        FIX R3: Use timezone.utc (not naive utcnow)
        """
        try:
            payload = request.get_json() or {}
            try:
                mode, files = _normalize_payload(payload)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

            run_id = str(uuid.uuid4())

            # FIX R1: Write RUNNING status BEFORE starting background process
            # This ensures GET /runs/<run_id> never returns 404
            started_at = datetime.now(timezone.utc)

            files_pending = (
                [{"original_name": f, "status": "PENDING"} for f in
                 files] if mode == "files" else [])

            initial_status = {
                "run_id": run_id,
                "status": "RUNNING",
                "requested_mode": mode,
                "mode": mode,  # backward compat
                "selected_mode": None,
                "started_at": started_at.isoformat(),
                "finished_at": None,
                "duration_ms": None,
                "files": files_pending,
                "summary": _summary_min(files if mode == "files" else []),
                "message": "Import in progress..."
            }

            write_log_atomic(run_id, initial_status)

            _db_registry_insert_start(run_id, mode, files, started_at)

            # Now start background process (daemon=False - survives worker restart)
            proc = multiprocessing.Process(
                target=execute_import_background,
                args=(run_id, mode, files),
                daemon=False
            )
            proc.start()

            return jsonify({
                "run_id": run_id,
                "status": "STARTED",
                "message": "Import started. Poll GET /runs/{run_id} for status"
            }), 202

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/ops/daily-import/run-sync", methods=["POST"])
    @require_api_key
    def ops_daily_import_run_sync():
        """
        POST /api/v1/ops/daily-import/run-sync
        Synchronous import (intended for short/local runs).
        DB registry: start + finish (best-effort); FS logs stay as fallback.
        """
        run_id = None
        mode = None
        files: list[str] = []
        started_at: datetime | None = None

        cmd: list[str] | None = None
        proc_result: subprocess.CompletedProcess[str] | None = None

        try:
            data = request.get_json(silent=True)

            if data is None:
                raw = (request.get_data(cache=False, as_text=True) or "").strip()

                if not raw:
                    return jsonify({
                        "error": "Missing JSON body",
                        "example": {"mode": "auto", "files": []},
                    }), 400

                err = {
                    "error": "Invalid JSON",
                    "hint": (
                        "PowerShell + curl.exe часто «съедает» кавычки, и сервер получает не-JSON "
                        "(например: {files:[],mode:auto}). "
                        "Используй Invoke-RestMethod или пайп в curl --data-binary '@-'."
                    ),
                    "example_ps_invoke_restmethod": (
                        "Invoke-RestMethod -Method Post -Uri $url "
                        "-Headers @{ 'X-API-Key' = $apiKey } "
                        "-ContentType 'application/json' -Body $body"
                    ),
                    "example_ps_curl_pipe": (
                        "$body | curl.exe -X POST $url "
                        "-H 'Content-Type: application/json' "
                        "-H \"X-API-Key: $apiKey\" "
                        "--data-binary '@-'"
                    ),
                    "example": {"mode": "auto", "files": []},
                }

                if OPS_DB_REGISTRY_DEBUG:
                    err["received_body_tail"] = _tail(raw, 200)

                return jsonify(err), 400

            if not isinstance(data, dict):
                return jsonify({
                    "error": "JSON body must be an object",
                    "example": {"mode": "auto", "files": []},
                }), 400

            try:
                mode, files = _normalize_payload(data)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

            run_id = str(uuid.uuid4())
            started_at = datetime.now(timezone.utc)

            files_pending = (
                [{"original_name": f, "status": "PENDING"} for f in
                 files] if mode == "files" else [])

            initial_status = {
                "run_id": run_id,
                "status": "RUNNING",
                "requested_mode": mode,
                "mode": mode,  # backward compat
                "selected_mode": None,
                "started_at": started_at.isoformat(),
                "finished_at": None,
                "duration_ms": None,
                "files": files_pending,
                "summary": _summary_min(files if mode == "files" else []),
                "message": "Import in progress...",
            }

            write_log_atomic(run_id, initial_status)

            # DB start (best-effort)
            try:
                _db_registry_insert_start(run_id, mode, files, started_at)
            except Exception as e:
                if OPS_DB_REGISTRY_DEBUG:
                    print(
                        f"[ops_daily_import] DB registry start failed (run_id={run_id}): {e!r}",
                        file=sys.stderr
                    )

            cmd = [
                sys.executable,
                "-m",
                "scripts.daily_import_ops",
                "--mode",
                mode,
                "--run-id",
                run_id,
                "--no-log-file",
            ]
            if mode == "files" and files:
                cmd.extend(["--files", *files])

            proc_result = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=SYNC_RUN_TIMEOUT_S,
                shell=False,
            )

            if proc_result.returncode != 0:
                raise RuntimeError(proc_result.stderr.strip() or "Import failed")

            import_result = json.loads(proc_result.stdout)
            if not isinstance(import_result, dict):
                import_result = {"result": import_result}

            # Ensure minimal keys for both FS + DB contracts
            import_result.setdefault("run_id", run_id)
            import_result.setdefault("mode", mode)  # backward compat
            import_result.setdefault("requested_mode", mode)
            import_result.setdefault("started_at", started_at.isoformat())

            import_result.setdefault("finished_at",
                                     datetime.now(timezone.utc).isoformat())

            write_log_atomic(run_id, import_result)

            # DB finish (best-effort); upsert saves even if start insert failed
            try:
                _db_registry_update_finish(run_id, mode, import_result)
            except Exception as e:
                if OPS_DB_REGISTRY_DEBUG:
                    print(
                        f"[ops_daily_import] DB registry finish failed (run_id={run_id}): {e!r}",
                        file=sys.stderr
                    )

            return jsonify(import_result), 200

        except subprocess.TimeoutExpired as e:
            finished_at = datetime.now(timezone.utc)

            duration_ms = _calc_duration_ms(started_at, finished_at)

            summary_min = _summary_min(files)

            stdout_raw = getattr(e, "stdout", None)
            if stdout_raw is None:
                stdout_raw = getattr(e, "output",
                                     None)  # TimeoutExpired.output == stdout

            stderr_raw = getattr(e, "stderr", None)

            timeout_result = {
                "run_id": run_id,
                "status": "TIMEOUT",
                "requested_mode": mode,
                "mode": mode,  # backward compat
                "files": files,
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat(),
                "duration_ms": duration_ms,
                "message": f"Import timeout (>{SYNC_RUN_TIMEOUT_S}s)",
                "hint": "Use async POST /run for long imports",
                "summary": summary_min,
                "exit_code": None,
                "stdout_tail": _tail(stdout_raw, STDIO_TAIL_CHARS),
                "stderr_tail": _tail(stderr_raw, STDIO_TAIL_CHARS),
            }

            if run_id:
                write_log_atomic(run_id, timeout_result)
                try:
                    _db_registry_update_finish(run_id, mode or "auto", timeout_result)
                except Exception as e:
                    if OPS_DB_REGISTRY_DEBUG:
                        print(
                            f"[ops_daily_import] DB registry finish failed (run_id={run_id}): {e!r}",
                            file=sys.stderr
                        )

            return jsonify(timeout_result), 504

        except json.JSONDecodeError as e:
            finished_at = datetime.now(timezone.utc)

            duration_ms = _calc_duration_ms(started_at, finished_at)

            summary_min = _summary_min(files)

            error_result = {
                "run_id": run_id,
                "status": "FAILED",
                "requested_mode": mode,
                "mode": mode,  # backward compat
                "files": files,
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat(),
                "duration_ms": duration_ms,
                "message": "Invalid JSON from orchestrator",
                "hint": "Check orchestrator stdout/stderr tails",
                "details": str(e),
                "summary": summary_min,
                "exit_code": proc_result.returncode if proc_result else None,
                "stdout_tail": _tail(proc_result.stdout if proc_result else
                                     None, STDIO_TAIL_CHARS),
                "stderr_tail": _tail(proc_result.stderr if proc_result else
                                     None, STDIO_TAIL_CHARS),
            }

            if run_id:
                write_log_atomic(run_id, error_result)
                try:
                    _db_registry_update_finish(run_id, mode or "auto", error_result)
                except Exception as e:
                    if OPS_DB_REGISTRY_DEBUG:
                        print(
                            f"[ops_daily_import] DB registry finish failed (run_id={run_id}): {e!r}",
                            file=sys.stderr
                        )

            return jsonify(error_result), 500

        except Exception as e:
            finished_at = datetime.now(timezone.utc)

            duration_ms = _calc_duration_ms(started_at, finished_at)

            summary_min = _summary_min(files)

            error_result = {
                "run_id": run_id,
                "status": "FAILED",
                "requested_mode": mode,
                "mode": mode,  # backward compat
                "files": files,
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat(),
                "duration_ms": duration_ms,
                "message": "Sync import failed",
                "details": str(e),
                "summary": summary_min,
                "exit_code": proc_result.returncode if proc_result else None,
                "stdout_tail": _tail(proc_result.stdout if proc_result else
                                     None, STDIO_TAIL_CHARS),
                "stderr_tail": _tail(proc_result.stderr if proc_result else
                                     None, STDIO_TAIL_CHARS),
            }

            if run_id:
                write_log_atomic(run_id, error_result)
                try:
                    _db_registry_update_finish(run_id, mode or "auto", error_result)
                except Exception as e:
                    if OPS_DB_REGISTRY_DEBUG:
                        print(
                            f"[ops_daily_import] DB registry finish failed (run_id={run_id}): {e!r}",
                            file=sys.stderr
                        )

            return jsonify(error_result), 500

    @app.route("/api/v1/ops/daily-import/runs", methods=["GET"])
    @require_api_key
    def ops_daily_import_runs():
        """
        GET /api/v1/ops/daily-import/runs

        Query:
          - limit: int (default=50, max=200)
          - cursor: opaque (optional)
          - status: string (optional)
          - from/to: ISO datetime (optional)

        Response:
          - items[] (stable contract)
          - runs[] alias (backward compat)
          - next_cursor (optional; null if no more)
        """
        try:
            # limit
            raw_limit = (request.args.get("limit") or "").strip() or "50"
            try:
                limit = int(raw_limit)
            except ValueError:
                return jsonify({"error": "Invalid limit"}), 400
            limit = max(1, min(limit, 200))

            cursor = (request.args.get("cursor") or "").strip() or None

            status = (request.args.get("status") or "").strip()
            if status:
                import re
                status = status.upper()
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", status):
                    return jsonify({"error": "Invalid status filter"}), 400

            from_arg = (request.args.get("from") or "").strip()
            to_arg = (request.args.get("to") or "").strip()

            from_dt = _iso_to_dt(from_arg) if from_arg else None
            to_dt = _iso_to_dt(to_arg) if to_arg else None

            if from_arg and from_dt is None:
                return jsonify({"error": "Invalid from datetime"}), 400
            if to_arg and to_dt is None:
                return jsonify({"error": "Invalid to datetime"}), 400

            def _respond(items: list[dict], has_more: bool):
                runs = [_legacy_from_item(i) for i in items]
                resp = {"items": items, "runs": runs, "next_cursor": None}

                if has_more and items:
                    last = items[-1]
                    last_dt = _iso_to_dt(last.get("started_at"))
                    if last_dt is not None and last.get("run_id"):
                        resp["next_cursor"] = _encode_cursor(last_dt,
                                                             str(last.get(
                                                                 "run_id")))

                return jsonify(resp), 200

            conn = _db_conn_or_none()

            # ---- DB-first ----
            if conn is not None:
                try:
                    where_clauses: list[str] = []
                    params: list[object] = []

                    if status:
                        where_clauses.append("status = %s")
                        params.append(status)

                    if from_dt is not None:
                        where_clauses.append("started_at >= %s")
                        params.append(from_dt)

                    if to_dt is not None:
                        where_clauses.append("started_at <= %s")
                        params.append(to_dt)

                    if cursor:
                        try:
                            dt, rid = _decode_cursor(cursor)
                        except ValueError:
                            return jsonify({"error": "Invalid cursor"}), 400
                        try:
                            rid = str(uuid.UUID(str(rid)))
                        except ValueError:
                            return jsonify({"error": "Invalid cursor"}), 400
                        where_clauses.append("(started_at, run_id) < (%s, %s)")
                        params.extend([dt, rid])

                    where = ""
                    if where_clauses:
                        where = "WHERE " + " AND ".join(where_clauses)

                    sql = f"""
                    SELECT
                      run_id::text as run_id,
                      status,
                      requested_mode,
                      selected_mode,
                      started_at,
                      finished_at,
                      duration_ms,
                      summary
                    FROM public.ops_daily_import_runs
                    {where}
                    ORDER BY started_at DESC, run_id DESC
                    LIMIT %s;
                    """
                    params.append(limit + 1)

                    rows = db_query(conn, sql, tuple(params)) or []
                    has_more = len(rows) > limit
                    page = rows[:limit]

                    items = [_item_from_db_row(r) for r in page]
                    return _respond(items, has_more)

                except Exception as e:
                    if OPS_DB_REGISTRY_DEBUG:
                        print(
                            f"[ops_daily_import] DB runs list failed; falling back to FS: {e!r}",
                            file=sys.stderr
                        )

                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            # ---- FS fallback (DB down / DB error) ----
            cursor_dt = cursor_rid = None
            if cursor:
                try:
                    cursor_dt, cursor_rid = _decode_cursor(cursor)
                except ValueError:
                    return jsonify({"error": "Invalid cursor"}), 400
                try:
                    cursor_rid = str(uuid.UUID(str(cursor_rid)))
                except ValueError:
                    return jsonify({"error": "Invalid cursor"}), 400

            items: list[dict] = []
            has_more = False

            if LOGS_DIR.exists():
                log_files = sorted(
                    LOGS_DIR.glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )

                for log_file in log_files:
                    run_id_guess = log_file.stem
                    started_dt = datetime.fromtimestamp(
                        log_file.stat().st_mtime, tz=timezone.utc)

                    try:
                        with open(log_file, "r", encoding="utf-8") as f:
                            run_data = json.load(f)

                        run_id_guess = str(
                            run_data.get("run_id") or run_id_guess)
                        started_dt = _iso_to_dt(
                            run_data.get("started_at")) or started_dt

                        summary = run_data.get("summary", {}) or {}
                        item = {
                            "run_id": run_id_guess,
                            "status": run_data.get("status"),
                            "requested_mode": run_data.get(
                                "requested_mode") or run_data.get("mode"),
                            "selected_mode": run_data.get("selected_mode"),
                            "started_at": _dt_to_iso(started_dt),
                            "finished_at": run_data.get("finished_at"),
                            "duration_ms": run_data.get("duration_ms"),
                            "summary": summary,
                        }

                    except json.JSONDecodeError:
                        # partial JSON while RUNNING
                        item = {
                            "run_id": run_id_guess,
                            "status": "RUNNING",
                            "requested_mode": None,
                            "selected_mode": None,
                            "started_at": _dt_to_iso(started_dt),
                            "finished_at": None,
                            "duration_ms": None,
                            "summary": {},
                        }

                    except IOError:
                        continue

                    # filters
                    if status and (
                            str(item.get("status") or "").upper() != status):
                        continue

                    item_dt = _iso_to_dt(item.get("started_at"))
                    if from_dt is not None and (
                            item_dt is None or item_dt < from_dt):
                        continue
                    if to_dt is not None and (
                            item_dt is None or item_dt > to_dt):
                        continue

                    if cursor_dt is not None and cursor_rid is not None:
                        try:
                            rid_val = str(uuid.UUID(str(item.get("run_id"))))
                        except Exception:
                            rid_val = str(item.get("run_id"))

                        if item_dt is None:
                            continue

                        if not ((item_dt, rid_val) < (cursor_dt, cursor_rid)):
                            continue

                    items.append(item)
                    if len(items) >= (limit + 1):
                        break

                # stable order (newest first)
                def _fs_sort_key(i: dict):
                    dt = _iso_to_dt(i.get("started_at"))
                    dt = dt or datetime(1970, 1, 1, tzinfo=timezone.utc)
                    rid = str(i.get("run_id") or "")
                    return (dt, rid)

                items.sort(key=_fs_sort_key, reverse=True)
                has_more = len(items) > limit
                items = items[:limit]

            return _respond(items, has_more)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/ops/daily-import/runs/<run_id>", methods=["GET"])
    @require_api_key
    def ops_daily_import_run_detail(run_id):
        """
        GET /api/v1/ops/daily-import/runs/{run_id} - run details (DB-first, FS fallback)

        Always returns a stable schema (even while RUNNING / partial JSON).
        """
        try:
            # validate UUID early
            try:
                run_id_norm = str(uuid.UUID(run_id))
            except ValueError:
                return jsonify({"error": "Invalid run_id"}), 400

            def _normalize_run_detail(payload: dict | None,
                                      row: dict | None) -> dict:
                out: dict = {}

                if isinstance(payload, dict):
                    out.update(payload)

                # map legacy field
                if out.get("requested_mode") is None and out.get("mode"):
                    out["requested_mode"] = out.get("mode")

                if row:
                    out.setdefault("run_id", row.get("run_id"))
                    out.setdefault("status", row.get("status"))
                    out.setdefault("requested_mode", row.get("requested_mode"))
                    out.setdefault("selected_mode", row.get("selected_mode"))
                    out.setdefault("started_at",
                                   _dt_to_iso(row.get("started_at")))
                    out.setdefault("finished_at",
                                   _dt_to_iso(row.get("finished_at")))
                    out.setdefault("duration_ms", row.get("duration_ms"))
                    if isinstance(row.get("summary"), dict):
                        out.setdefault("summary", row.get("summary") or {})

                # backward compat
                if out.get("requested_mode") and "mode" not in out:
                    out["mode"] = out.get("requested_mode")

                # normalize timestamps (if someone put datetime objects)
                if isinstance(out.get("started_at"), datetime):
                    out["started_at"] = _dt_to_iso(out.get("started_at"))
                if isinstance(out.get("finished_at"), datetime):
                    out["finished_at"] = _dt_to_iso(out.get("finished_at"))

                # normalize summary
                if not isinstance(out.get("summary"), dict):
                    out["summary"] = {}

                # normalize files: list[str] -> list[dict]
                files_val = out.get("files")
                if files_val is None:
                    out["files"] = []
                elif isinstance(files_val, list) and files_val and isinstance(
                        files_val[0], str):
                    out["files"] = [{"original_name": s, "status": "PENDING"}
                                    for s in files_val]

                # Ensure minimal keys
                out.setdefault("run_id", run_id_norm)
                out.setdefault("status", out.get("status") or "RUNNING")
                out.setdefault("selected_mode", out.get("selected_mode"))
                out.setdefault("finished_at", out.get("finished_at"))
                out.setdefault("duration_ms", out.get("duration_ms"))

                return out

            conn = _db_conn_or_none()

            # ---- DB-first ----
            if conn is not None:
                try:
                    sql = """
                          SELECT run_id::text as run_id, status,
                                 requested_mode,
                                 selected_mode,
                                 started_at,
                                 finished_at,
                                 duration_ms,
                                 summary,
                                 result_json,
                                 log_relpath
                          FROM public.ops_daily_import_runs
                          WHERE run_id = %s LIMIT 1;
                          """
                    rows = db_query(conn, sql, (run_id_norm,)) or []
                    if rows:
                        row = rows[0]
                        payload = row.get("result_json") if isinstance(
                            row.get("result_json"), dict) else None
                        return jsonify(
                            _normalize_run_detail(payload, row)), 200

                except Exception as e:
                    if OPS_DB_REGISTRY_DEBUG:
                        print(
                            f"[ops_daily_import] DB run detail failed; falling back to FS (run_id={run_id_norm}): {e!r}",
                            file=sys.stderr
                        )

                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            # ---- FS fallback ----
            log_file = LOGS_DIR / f"{run_id_norm}.json"
            if not log_file.exists():
                return jsonify({"error": "Run not found"}), 404

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    run_data = json.load(f)
                return jsonify(_normalize_run_detail(run_data, None)), 200

            except json.JSONDecodeError:
                # partial JSON while RUNNING
                started_dt = datetime.fromtimestamp(log_file.stat().st_mtime,
                                                    tz=timezone.utc)
                payload = {
                    "run_id": run_id_norm,
                    "status": "RUNNING",
                    "started_at": started_dt.isoformat(),
                    "finished_at": None,
                    "duration_ms": None,
                    "files": [],
                    "summary": {},
                    "message": "Import in progress (log updating)...",
                }
                return jsonify(_normalize_run_detail(payload, None)), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/ops/files/<kind>/<path:relpath>", methods=["GET"])
    @require_api_key
    def ops_download_file(kind, relpath):
        """
        GET /api/v1/ops/files/{kind}/{relpath} - download files

        Security: is_relative_to() path traversal protection (from v1.2.2.1)
        """
        try:
            if kind == "archive":
                base = ARCHIVE_DIR
            elif kind == "quarantine":
                base = QUARANTINE_DIR
            elif kind == "logs":
                base = LOGS_DIR
            else:
                return jsonify({"error": "Invalid kind"}), 400

            # Path traversal protection: is_relative_to() or commonpath
            file_path = (base / relpath).resolve()
            base_resolved = base.resolve()

            try:
                # Python 3.9+
                if not file_path.is_relative_to(base_resolved):
                    return jsonify({"error": "Path traversal blocked"}), 403
            except AttributeError:
                # Python 3.8 fallback
                try:
                    common = os.path.commonpath([base_resolved, file_path])
                    if common != str(base_resolved):
                        return jsonify({"error": "Path traversal blocked"}), 403
                except ValueError:
                    return jsonify({"error": "Path traversal blocked"}), 403

            if not file_path.exists():
                return jsonify({"error": "File not found"}), 404

            return send_file(str(file_path), as_attachment=True)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    print("✅ Ops Daily Import endpoints registered (v1.2.2.2 FINAL-STABLE)")
    print("   • R1: RUNNING log written BEFORE proc.start() (no 404!)")
    print("   • R2: proc.kill() on timeout + status=TIMEOUT")
    print("   • R3: timezone.utc everywhere (aware timestamps)")
    print("   • P1: run-sync also uses --run-id (consistent history)")
    print("   • P2: status=TIMEOUT (separate from FAILED)")
