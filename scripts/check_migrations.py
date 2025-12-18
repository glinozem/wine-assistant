#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

RE_ALLOWED_CANONICAL = re.compile(r"^\d{4}_.+\.sql$", re.IGNORECASE)
RE_DATE_STYLE = re.compile(r"^\d{4}-\d{2}-\d{2}-", re.IGNORECASE)

def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    migrations_dir = repo_root / "db" / "migrations"

    if not migrations_dir.exists():
        print(f"[check_migrations] ERROR: not found: {migrations_dir}")
        return 2

    violations: list[str] = []

    for path in migrations_dir.rglob("*.sql"):
        rel = path.relative_to(migrations_dir)
        parts = rel.parts

        # allow anything under _legacy (including nested dirs)
        if parts and parts[0] == "_legacy":
            continue

        # canonical migrations MUST be directly under db/migrations (no extra subdirs)
        if len(parts) != 1:
            violations.append(f"{rel.as_posix()} (canonical migrations must be in db/migrations root; only _legacy/ may be a subdir)")
            continue

        filename = path.name

        if RE_DATE_STYLE.match(filename):
            violations.append(f"{rel.as_posix()} (date-based legacy file must be under _legacy/)")
            continue

        if not RE_ALLOWED_CANONICAL.match(filename):
            violations.append(f"{rel.as_posix()} (invalid canonical migration name; expected NNNN_*.sql)")
            continue

    if violations:
        print("[check_migrations] ERROR: migration layout violations found:")
        for v in violations:
            print(f" - {v}")
        print("\nRules:")
        print(" - Canonical migrations MUST be db/migrations/NNNN_*.sql (root only)")
        print(" - Legacy scripts MUST be placed under db/migrations/_legacy/")
        return 1

    print("[check_migrations] OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
