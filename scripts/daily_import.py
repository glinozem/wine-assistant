"""Daily incremental import.

This script is intentionally conservative: it reuses the existing importer
(scripts.load_csv) and only orchestrates the steps required for a daily run.

Key properties
- Incremental: no volume wipes, no bootstrap.
- Idempotent at the file level: scripts.load_csv uses ingest_envelope(file_sha256)
  and prints "[SKIP]" when the same file is re-run.
- Safe against parallel runs: uses a Postgres advisory lock.
- Operational hygiene: moves processed files out of data/inbox.

Typical usage
  python -m scripts.daily_import                 # pick newest .xlsx from data/inbox
  python -m scripts.daily_import --files a.xlsx b.xlsx

Exit codes
  0 - success (including the case when all files were SKIP)
  1 - at least one file failed to import
  2 - could not acquire advisory lock (another run in progress)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import psycopg2
from dotenv import load_dotenv

LOCK_NAME = "wine-assistant:daily-import:v1"


@dataclass
class FileResult:
    path: Path
    status: str  # imported | skipped | failed
    archived_to: Path | None = None


def _project_root() -> Path:
    # scripts/ is in the project root.
    return Path(__file__).resolve().parents[1]


def _lock_keys(name: str) -> Tuple[int, int]:
    """Derive a stable (key1, key2) pair for pg_(try_)advisory_lock(int,int)."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    key1 = int.from_bytes(digest[0:4], byteorder="big", signed=False)
    key2 = int.from_bytes(digest[4:8], byteorder="big", signed=False)
    # Postgres expects signed 32-bit ints for the (int,int) variant.
    def to_signed_32(v: int) -> int:
        return v - 2**32 if v >= 2**31 else v

    return to_signed_32(key1), to_signed_32(key2)


class AdvisoryLock:
    def __init__(self, conn, name: str):
        self.conn = conn
        self.name = name
        self.key1, self.key2 = _lock_keys(name)
        self.acquired = False

    def try_acquire(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s, %s)", (self.key1, self.key2))
            self.acquired = bool(cur.fetchone()[0])
        return self.acquired

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s, %s)", (self.key1, self.key2))
            self.conn.commit()
        finally:
            self.acquired = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _stream_subprocess(cmd: List[str], cwd: Path) -> Tuple[int, str]:
    """Run a command, stream output to console, and return (rc, combined_output)."""
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert proc.stdout is not None

    out_lines: List[str] = []
    for line in proc.stdout:
        print(line, end="")
        out_lines.append(line)

    rc = proc.wait()
    return rc, "".join(out_lines)


def _ensure_unique_path(dst: Path) -> Path:
    if not dst.exists():
        return dst

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent
    for i in range(1, 10_000):
        candidate = parent / f"{stem}__{i}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find a free archive name for: {dst}")


def _move_file(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst = _ensure_unique_path(dst)

    try:
        shutil.move(str(src), str(dst))
    except Exception:
        # Fallback: copy+unlink (useful for cross-device moves).
        shutil.copy2(str(src), str(dst))
        src.unlink(missing_ok=True)

    return dst


def _select_newest_xlsx(inbox: Path) -> Path | None:
    candidates = [p for p in inbox.glob("*.xlsx") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _sql_maintenance(conn) -> None:
    """Small corrective SQL steps (safe/idempotent)."""
    with conn.cursor() as cur:
        # 1) Normalize whitespace in wineries.producer_site.
        cur.execute(
            """
            UPDATE wineries
               SET producer_site = regexp_replace(producer_site, '\\s+', '', 'g')
             WHERE producer_site IS NOT NULL
               AND producer_site ~ '\\s';
            """
        )

        # 2) Backfill products.region from wineries.
        cur.execute(
            """
            UPDATE products p
               SET region = w.region
              FROM wineries w
             WHERE p.supplier = w.supplier
               AND p.region IS NULL
               AND w.region IS NOT NULL;
            """
        )

        # 3) Backfill products.producer_site from wineries when NULL/invalid.
        #    - invalid: any non-ASCII printable: [^ -~]
        #    - or contains whitespace.
        cur.execute(
            """
            UPDATE products p
               SET producer_site = regexp_replace(w.producer_site, '\\s+', '', 'g')
              FROM wineries w
             WHERE p.supplier = w.supplier
               AND (p.producer_site IS NULL OR p.producer_site ~ '[^ -~]' OR p.producer_site ~ '\\s')
               AND w.producer_site IS NOT NULL;
            """
        )

        # 4) Ensure wineries rows exist for all suppliers present in products.
        #    (region/site can be enriched later).
        cur.execute(
            """
            INSERT INTO wineries (supplier, supplier_ru)
            SELECT DISTINCT p.supplier, NULL
              FROM products p
              LEFT JOIN wineries w ON w.supplier = p.supplier
             WHERE p.supplier IS NOT NULL
               AND w.supplier IS NULL;
            """
        )

    conn.commit()


def _run_python_module(module: str, args: List[str], cwd: Path) -> Tuple[int, str]:
    cmd = [sys.executable, "-m", module, *args]
    return _stream_subprocess(cmd, cwd=cwd)


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily incremental import")

    p.add_argument(
        "--inbox",
        default=str(Path("data") / "inbox"),
        help="Inbox directory (default: data/inbox)",
    )
    p.add_argument(
        "--archive",
        default=str(Path("data") / "archive"),
        help="Archive directory (default: data/archive)",
    )
    p.add_argument(
        "--quarantine",
        default=str(Path("data") / "quarantine"),
        help="Quarantine directory (default: data/quarantine)",
    )
    p.add_argument(
        "--files",
        nargs="+",
        help="Explicit list of Excel files to import",
    )

    p.add_argument(
        "--wineries-excel",
        default=str(Path("data") / "catalog" / "wineries_enrichment_from_pdf_norm.xlsx"),
        help="Excel file for wineries catalog load (default: data/catalog/wineries_enrichment_from_pdf_norm.xlsx)",
    )
    p.add_argument(
        "--enrich-excel",
        default=None,
        help="Excel file for enrich_producers. If not set, uses --wineries-excel.",
    )

    p.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip wineries/enrich steps",
    )
    p.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip inventory history snapshot",
    )
    p.add_argument(
        "--snapshot-dry-run-first",
        action="store_true",
        help="Run sync_inventory_history --dry-run before applying",
    )

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    root = _project_root()
    os.chdir(root)  # load_dotenv() searches current working directory.
    load_dotenv()

    inbox = Path(args.inbox)
    archive_root = Path(args.archive)
    quarantine_root = Path(args.quarantine)

    files: list[Path]
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        newest = _select_newest_xlsx(inbox)
        if newest is None:
            print(f"[daily-import] No .xlsx files found in inbox: {inbox}")
            return 0
        files = [newest]

    # Validate files early.
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        print("[daily-import] Missing file(s):")
        for m in missing:
            print(f"  - {m}")
        return 1

    # Acquire lock.
    from scripts.load_utils import get_conn  # local import to ensure .env is loaded.

    conn = get_conn()
    conn.autocommit = False

    imported_any = False
    failures_any = False
    results: List[FileResult] = []

    with conn:
        with AdvisoryLock(conn, LOCK_NAME) as lock:
            if not lock.try_acquire():
                print("[daily-import] Another daily import is already running (advisory lock not acquired).")
                return 2

            for src in files:
                # 1) Import
                print(f"\n=== IMPORT (load_csv) ===\n>>> File: {src}")
                rc, output = _run_python_module("scripts.load_csv", ["--excel", str(src)], cwd=root)

                skipped = "[SKIP]" in output
                if rc != 0:
                    failures_any = True
                    status = "failed"
                elif skipped:
                    status = "skipped"
                else:
                    imported_any = True
                    status = "imported"

                # 2) Move to archive/quarantine (archive also for SKIP)
                month = datetime.now().strftime("%Y-%m")
                if status == "failed":
                    dst = quarantine_root / month / src.name
                else:
                    dst = archive_root / month / src.name

                try:
                    archived_to = _move_file(src, dst)
                    print(f"[daily-import] Moved: {src} -> {archived_to}")
                except Exception as e:
                    failures_any = True
                    archived_to = None
                    print(f"[daily-import] ERROR: could not move file to {dst}: {e}")

                results.append(FileResult(path=src, status=status, archived_to=archived_to))

            # 3) Enrich / backfill / snapshot (only if something actually imported)
            if imported_any:
                if not args.no_enrich:
                    wineries_excel = Path(args.wineries_excel)
                    enrich_excel = Path(args.enrich_excel) if args.enrich_excel else wineries_excel

                    if wineries_excel.exists():
                        print("\n=== LOAD WINERIES CATALOG (load_wineries) ===")
                        rc, _ = _run_python_module(
                            "scripts.load_wineries",
                            ["--excel", str(wineries_excel), "--apply"],
                            cwd=root,
                        )
                        if rc != 0:
                            failures_any = True

                    if enrich_excel.exists():
                        print("\n=== ENRICH PRODUCTS (enrich_producers) ===")
                        rc, _ = _run_python_module(
                            "scripts.enrich_producers",
                            ["--excel", str(enrich_excel), "--apply"],
                            cwd=root,
                        )
                        if rc != 0:
                            failures_any = True

                    print("\n=== MAINTENANCE SQL (backfills/normalization) ===")
                    try:
                        _sql_maintenance(conn)
                        print("[daily-import] Maintenance SQL completed")
                    except Exception as e:
                        failures_any = True
                        print(f"[daily-import] ERROR: maintenance SQL failed: {e}")
                        conn.rollback()

                if not args.no_snapshot:
                    print("\n=== INVENTORY HISTORY SNAPSHOT (sync_inventory_history) ===")
                    if args.snapshot_dry_run_first:
                        rc, _ = _run_python_module(
                            "scripts.sync_inventory_history",
                            ["--dry-run"],
                            cwd=root,
                        )
                        if rc != 0:
                            failures_any = True

                    rc, _ = _run_python_module("scripts.sync_inventory_history", [], cwd=root)
                    if rc != 0:
                        failures_any = True
            else:
                print("\n[daily-import] All files were SKIP; enrich/snapshot steps are not executed.")

    # Summary
    print("\n=== SUMMARY ===")
    for r in results:
        dst = str(r.archived_to) if r.archived_to else "(not moved)"
        print(f"- {r.status.upper():8} {r.path.name} -> {dst}")

    if failures_any:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
