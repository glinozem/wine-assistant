#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

RE_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(?:public\.)?([a-zA-Z0-9_]+)\s*\((.*?)\);\s*",
    re.IGNORECASE | re.DOTALL,
)

FORBIDDEN = [
    re.compile(r"\bembedding\b", re.IGNORECASE),
    re.compile(r"\bivfflat\b", re.IGNORECASE),
    re.compile(r"CREATE\s+INDEX\b", re.IGNORECASE),
    re.compile(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\b", re.IGNORECASE),
    re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", re.IGNORECASE),
]

REQUIRED_TABLES = {"products", "inventory"}

REQUIRED_PRODUCTS_COLS = {
    "code",
    "producer",
    "title_ru",
    "title_en",
    "country",
    "region",
    "color",
    "style",
    "grapes",
    "abv",
    "pack",
    "volume",
    "price_rub",
    "search_text",
}

REQUIRED_INVENTORY_COLS = {"code", "stock_total", "reserved", "stock_free", "asof_date"}


def _extract_columns(table_body: str) -> set[str]:
    cols: set[str] = set()
    for raw in table_body.splitlines():
        line = raw.strip()
        if not line or line.startswith("--"):
            continue

        token = re.split(r"\s+", line, maxsplit=1)[0].strip().strip(",").strip('"').lower()
        if token in {"constraint", "primary", "unique", "check", "foreign"}:
            continue

        if token:
            cols.add(token)
    return cols


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    init_sql = repo_root / "db" / "init.sql"

    if not init_sql.exists():
        print(f"[db_bootstrap_contract] ERROR: not found: {init_sql}")
        return 2

    sql = init_sql.read_text(encoding="utf-8")

    # forbid “heavy”/drifting constructs in init.sql
    for rx in FORBIDDEN:
        if rx.search(sql):
            print(f"[db_bootstrap_contract] ERROR: forbidden construct in db/init.sql: {rx.pattern}")
            return 1

    tables = {}
    for name, body in RE_CREATE_TABLE.findall(sql):
        tname = name.lower()
        tables[tname] = _extract_columns(body)

    found_tables = set(tables.keys())
    if found_tables != REQUIRED_TABLES:
        print("[db_bootstrap_contract] ERROR: init.sql must define ONLY these tables:")
        print(f"  required: {sorted(REQUIRED_TABLES)}")
        print(f"  found:    {sorted(found_tables)}")
        return 1

    missing_prod = REQUIRED_PRODUCTS_COLS - tables["products"]
    if missing_prod:
        print("[db_bootstrap_contract] ERROR: products table missing required columns:")
        print("  " + ", ".join(sorted(missing_prod)))
        return 1

    missing_inv = REQUIRED_INVENTORY_COLS - tables["inventory"]
    if missing_inv:
        print("[db_bootstrap_contract] ERROR: inventory table missing required columns:")
        print("  " + ", ".join(sorted(missing_inv)))
        return 1

    print("[db_bootstrap_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
