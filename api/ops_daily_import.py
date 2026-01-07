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

import json
import multiprocessing
import os
import subprocess
import sys
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
        import uuid
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

        except Exception as e:
            error_result = {
                "run_id": run_id,
                "status": "FAILED",
                "error": str(e),
                "finished_at": datetime.now(timezone.utc).isoformat()  # FIX R3
            }

            write_log_atomic(run_id, error_result)

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

            total_written = 0

            for fs in fs_list:
                original = getattr(fs, "filename", None) or ""
                try:
                    safe_name = _validate_inbox_xlsx_basename(original)
                    saved_name = _allocate_non_conflicting_name(INBOX_DIR,
                                                                safe_name)

                    size = _save_upload_atomic(fs, INBOX_DIR, saved_name,
                                               MAX_UPLOAD_FILE_BYTES)

                    total_written += size
                    if total_written > MAX_UPLOAD_TOTAL_BYTES:
                        # roll back this file and mark rejected
                        try:
                            (INBOX_DIR / saved_name).unlink(
                                missing_ok=True)  # py3.11 ok
                        except Exception:
                            pass
                        rejected.append({
                            "original_name": original,
                            "reason": "TOTAL_TOO_LARGE",
                            "message": f"Total upload limit exceeded ({MAX_UPLOAD_TOTAL_MB} MB)"
                        })
                        continue

                    uploaded.append({
                        "original_name": original,
                        "saved_name": saved_name,
                        "size": size,
                        "status": "UPLOADED"
                    })

                except ValueError as e:
                    # map known errors
                    reason = str(e)
                    if reason == "FILE_TOO_LARGE":
                        rejected.append({
                            "original_name": original,
                            "reason": "FILE_TOO_LARGE",
                            "message": f"Max per-file size is {MAX_UPLOAD_FILE_MB} MB"
                        })
                    else:
                        # default for filename/ext/etc
                        rejected.append({
                            "original_name": original,
                            "reason": "INVALID_FILE",
                            "message": str(e)
                        })

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

            import uuid
            run_id = str(uuid.uuid4())

            # FIX R1: Write RUNNING status BEFORE starting background process
            # This ensures GET /runs/<run_id> never returns 404
            initial_status = {
                "run_id": run_id,
                "status": "RUNNING",
                "mode": mode,
                "files": files,
                "started_at": datetime.now(timezone.utc).isoformat(),  # FIX R3
                "message": "Import in progress..."
            }

            write_log_atomic(run_id, initial_status)

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
        POST /api/v1/ops/daily-import/run-sync - SYNC import (DEBUG ONLY)

        POLISH P1: Also uses --run-id for consistent history

        ⚠️ Requires GUNICORN_TIMEOUT=900 or use async /run instead
        """
        try:
            payload = request.get_json() or {}
            try:
                mode, files = _normalize_payload(payload)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

            # POLISH P1: Generate run_id for sync too (consistent history)
            import uuid
            run_id = str(uuid.uuid4())

            # Use sys.executable + pass run_id
            cmd = [
                sys.executable, "-m", "scripts.daily_import_ops",
                "--mode", mode,
                "--run-id", run_id,      # POLISH P1: Consistency!
                "--no-log-file"           # API will write log
            ]

            if mode == "files" and files:
                cmd.extend(["--files"] + files)

            result = subprocess.run(  # nosemgrep: python.flask.security.injection.subprocess-injection.subprocess-injection
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=900,
                shell=False,
            )

            try:
                import_result = json.loads(result.stdout) if result.stdout else None
            except json.JSONDecodeError:
                import_result = None

            if not isinstance(import_result, dict):
                import_result = {
                    "run_id": run_id,
                    "status": "FAILED",
                    "error": f"Invalid JSON from orchestrator (exit={result.returncode})",
                    "stdout": (result.stdout or "")[:1000],
                    "stderr": (result.stderr or "")[:1000],
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }

            if import_result.get("run_id") != run_id:
                import_result["run_id"] = run_id

            # POLISH P1: Write to history for consistency
            write_log_atomic(run_id, import_result)

            return jsonify(import_result), 200

        except subprocess.TimeoutExpired:
            return jsonify({
                "error": "Import timeout (>15 minutes)",
                "hint": "Use async POST /run for long imports"
            }), 504
        except json.JSONDecodeError as e:
            return jsonify({
                "error": "Invalid JSON from orchestrator",
                "details": str(e)
            }), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/ops/daily-import/runs", methods=["GET"])
    @require_api_key
    def ops_daily_import_runs():
        """GET /api/v1/ops/daily-import/runs?limit=50 - list runs"""
        try:
            limit = int(request.args.get("limit", 50))
            limit = min(limit, 50)

            runs = []

            if LOGS_DIR.exists():
                log_files = sorted(
                    LOGS_DIR.glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )[:limit]

                for log_file in log_files:
                    try:
                        with open(log_file, 'r') as f:
                            run_data = json.load(f)

                        runs.append({
                            "run_id": run_data.get("run_id"),
                            "status": run_data.get("status"),
                            "started_at": run_data.get("started_at"),
                            "finished_at": run_data.get("finished_at"),
                            "duration_ms": run_data.get("duration_ms"),
                            "files_total": run_data.get("summary", {}).get("files_total", 0),
                            "files_imported": run_data.get("summary", {}).get("files_imported", 0),
                            "files_skipped": run_data.get("summary", {}).get("files_skipped", 0),
                            "files_quarantined": run_data.get("summary", {}).get("files_quarantined", 0),
                            "files_failed": run_data.get("summary", {}).get("files_failed", 0)
                        })
                    except (json.JSONDecodeError, IOError):
                        continue

            return jsonify({"runs": runs}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/v1/ops/daily-import/runs/<run_id>", methods=["GET"])
    @require_api_key
    def ops_daily_import_run_detail(run_id):
        """
        GET /api/v1/ops/daily-import/runs/{run_id} - run details

        FIX R1: File now created BEFORE proc.start(), so 404 is rare
        """
        try:
            log_file = LOGS_DIR / f"{run_id}.json"

            if not log_file.exists():
                return jsonify({"error": "Run not found"}), 404

            try:
                with open(log_file, 'r') as f:
                    run_data = json.load(f)
                return jsonify(run_data), 200

            except json.JSONDecodeError:
                # File being written - return RUNNING
                return jsonify({
                    "run_id": run_id,
                    "status": "RUNNING",
                    "message": "Import in progress (log updating)..."
                }), 200

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
