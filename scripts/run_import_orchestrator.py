from __future__ import annotations

import argparse
import logging
import os
from datetime import date

from scripts.db_connect import connect_postgres
from scripts.import_orchestrator import load_callable, run_import_orchestrator


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run import orchestrator (registry + optional envelope).")
    parser.add_argument("--supplier", required=True)
    parser.add_argument("--file", required=True, dest="file_path")
    parser.add_argument("--as-of-date", required=True, type=_parse_date)
    parser.add_argument("--triggered-by", default=os.getenv("USERNAME") or os.getenv("USER") or "cli")
    parser.add_argument("--import-fn", required=True, help="Python callable spec: module:callable")
    parser.add_argument("--processing-mode", default="atomic", choices=["atomic", "chunked"])
    parser.add_argument("--no-skipped-audit-row", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    import_fn = load_callable(args.import_fn)

    conn = connect_postgres()
    try:
        res = run_import_orchestrator(
            conn,
            supplier=args.supplier,
            file_path=args.file_path,
            as_of_date=args.as_of_date,
            triggered_by=args.triggered_by,
            import_fn=import_fn,
            processing_mode=args.processing_mode,
            create_skipped_audit_row=not args.no_skipped_audit_row,
        )
        if res.status == "failed":
            return 2
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
