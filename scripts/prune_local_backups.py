"""Prune local PostgreSQL dump files in ./backups (or another directory).

This replaces complex one-liners in Makefile and provides optional structured
logging compatible with Promtail/Loki.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path
from typing import List, Optional

from scripts.emit_event import Event, emit


def prune(backups_dir: Path, db_name: str, keep: int) -> dict:
    backups_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(backups_dir / f"{db_name}_*.dump")
    files: List[str] = sorted(glob.glob(pattern), reverse=True)

    kept = files[:keep]
    to_delete = files[keep:]

    for f in to_delete:
        Path(f).unlink(missing_ok=True)

    return {
        "found_count": len(files),
        "kept_count": len(kept),
        "deleted_count": len(to_delete),
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.prune_local_backups")
    p.add_argument("--backups-dir", default="backups", help="Backups directory (default: backups)")
    p.add_argument("--db-name", default="wine_db", help="DB name used in dump file names (default: wine_db)")
    p.add_argument("--keep", type=int, default=10, help="How many newest dumps to keep (default: 10)")
    p.add_argument("--log-file", default=None, help="Optional JSONL event log file path")
    args = p.parse_args(argv)

    backups_dir = Path(args.backups_dir)
    res = prune(backups_dir=backups_dir, db_name=args.db_name, keep=args.keep)

    print(f"[prune-local] found={res['found_count']} keep={args.keep} deleted={res['deleted_count']}")
    if args.log_file:
        emit(
            Event(
                level="info",
                service="backup",
                event="prune_local_completed",
                fields={"keep": args.keep, **res},
            ),
            log_file=Path(args.log_file),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
