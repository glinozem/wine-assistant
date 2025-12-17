#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cleanup_test_data.py

Deletes "test" products (and their dependent rows) from a Postgres DB.

Default matching rule:
  - product code starts with INTTEST_   (case-insensitive)

Safe by default:
  - DRY-RUN mode (no writes) unless --apply is provided.
  - Prints a deletion plan (counts per table) before executing.

Works well with Docker Compose setups where Postgres is exposed to the host.
The script can read connection settings from:
  - DATABASE_URL
  - DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
  - PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
It can also load a project .env file.

Examples:
  # Dry-run (default)
  python scripts/cleanup_test_data.py

  # Apply deletions
  python scripts/cleanup_test_data.py --apply

  # Custom prefixes / patterns
  python scripts/cleanup_test_data.py --prefix INTTEST_ --prefix DEMO_ --apply
  python scripts/cleanup_test_data.py --pattern "INTTEST\_%" --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg2
import psycopg2.extras

# ----------------------------
# .env loader (dependency-free)
# ----------------------------

def load_dotenv_file(path: Optional[str], override: bool = False) -> int:
    """
    Load KEY=VALUE pairs from a .env-like file into os.environ.

    Returns number of variables loaded.
    """
    if not path:
        return 0
    p = Path(path)
    if not p.exists() or not p.is_file():
        return 0

    loaded = 0
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        # strip optional quotes
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
            v = v[1:-1]
        if override or (os.getenv(k) is None):
            os.environ[k] = v
            loaded += 1
    return loaded


# ----------------------------
# LIKE / ILIKE helpers
# ----------------------------

ESC = "\\"

def escape_like_literal(s: str, escape_char: str = ESC) -> str:
    """
    Escape a literal string so it can be safely used in a LIKE/ILIKE pattern
    with ESCAPE '\\'. Escapes: backslash, %, _
    """
    if s is None:
        return ""
    out = []
    for ch in str(s):
        if ch in (escape_char, "%", "_"):
            out.append(escape_char)
        out.append(ch)
    return "".join(out)


def patterns_from_prefixes(prefixes: Sequence[str]) -> List[str]:
    # Prefix means "starts with", so we append "%"
    return [escape_like_literal(p) + "%" for p in prefixes if p]


def build_ilike_clause(column_sql: str, patterns: Sequence[str]) -> Tuple[str, List[str]]:
    """
    Build an ILIKE (OR...) clause with ESCAPE '\' and params.

    Example output:
      "(code ILIKE %s ESCAPE '\' OR code ILIKE %s ESCAPE '\')", [p1, p2]
    """
    pats = [p for p in patterns if p]
    if not pats:
        return "FALSE", []
    pieces = [f"{column_sql} ILIKE %s ESCAPE '{ESC}'" for _ in pats]
    return "(" + " OR ".join(pieces) + ")", list(pats)


# ----------------------------
# DB discovery helpers
# ----------------------------

@dataclass(frozen=True)
class TableRef:
    schema: str
    name: str

    def qname(self) -> str:
        return f"{quote_ident(self.schema)}.{quote_ident(self.name)}"


@dataclass(frozen=True)
class FKRef:
    child: TableRef
    child_column: str
    parent: TableRef
    parent_column: str


def quote_ident(ident: str) -> str:
    # Minimal identifier quoting (safe for Postgres).
    return '"' + str(ident).replace('"', '""') + '"'


def project_root() -> Path:
    # scripts/cleanup_test_data.py -> repo root is one level up
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        return Path.cwd()


def build_dsn(_args=None) -> str:
    """
    Build DSN from environment.

    Priority:
      1) DATABASE_URL (if present)
      2) DB_* variables
      3) PG* variables
      4) defaults
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("DB_HOST") or os.getenv("PGHOST") or "localhost"
    port = os.getenv("DB_PORT") or os.getenv("PGPORT") or "5432"
    db = os.getenv("DB_NAME") or os.getenv("PGDATABASE") or "postgres"
    user = os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
    password = os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or ""

    # psycopg2 DSN format
    parts = [f"host={host}", f"port={port}", f"dbname={db}", f"user={user}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def list_tables(conn, schema: str) -> List[TableRef]:
    sql = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema,))
        return [TableRef(r[0], r[1]) for r in cur.fetchall()]


def table_columns(conn, table: TableRef) -> List[str]:
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table.schema, table.name))
        return [r[0] for r in cur.fetchall()]


def pick_main_table(conn, schema: str, explicit_table: Optional[str]) -> TableRef:
    if explicit_table:
        return TableRef(schema, explicit_table)

    tables = list_tables(conn, schema)
    if not tables:
        raise RuntimeError(f"No tables found in schema: {schema}")

    # Prefer canonical name
    for t in tables:
        if t.name == "products":
            return t

    # Fallback: first table
    return tables[0]


def resolve_code_column(conn, table: TableRef, explicit_col: Optional[str]) -> str:
    if explicit_col:
        return explicit_col

    cols = table_columns(conn, table)
    # Common options (order matters)
    for c in ("code", "sku", "sku_code", "product_code"):
        if c in cols:
            return c

    raise RuntimeError(f"Cannot guess code column for {table.schema}.{table.name}. Columns: {cols}")


def find_fk_deps(conn, parent: TableRef) -> List[FKRef]:
    """
    Find FK dependencies referencing parent table, returning per-column mapping.
    """
    sql = """
    SELECT
      nsp_child.nspname  AS child_schema,
      rel_child.relname  AS child_table,
      att_child.attname  AS child_column,
      nsp_parent.nspname AS parent_schema,
      rel_parent.relname AS parent_table,
      att_parent.attname AS parent_column
    FROM pg_constraint con
    JOIN pg_class rel_child   ON rel_child.oid = con.conrelid
    JOIN pg_namespace nsp_child ON nsp_child.oid = rel_child.relnamespace
    JOIN pg_class rel_parent  ON rel_parent.oid = con.confrelid
    JOIN pg_namespace nsp_parent ON nsp_parent.oid = rel_parent.relnamespace
    JOIN LATERAL unnest(con.conkey)  WITH ORDINALITY AS ck(attnum, ord) ON TRUE
    JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = ck.ord
    JOIN pg_attribute att_child  ON att_child.attrelid = con.conrelid  AND att_child.attnum  = ck.attnum
    JOIN pg_attribute att_parent ON att_parent.attrelid = con.confrelid AND att_parent.attnum = fk.attnum
    WHERE con.contype = 'f'
      AND nsp_parent.nspname = %s
      AND rel_parent.relname = %s
    ORDER BY child_schema, child_table, child_column
    """
    with conn.cursor() as cur:
        cur.execute(sql, (parent.schema, parent.name))
        rows = cur.fetchall()

    out: List[FKRef] = []
    for r in rows:
        out.append(FKRef(
            child=TableRef(r[0], r[1]),
            child_column=r[2],
            parent=TableRef(r[3], r[4]),
            parent_column=r[5],
        ))
    return out


def find_other_code_tables(conn, schema: str, code_column: str, parent: TableRef, exclude: Sequence[TableRef]) -> List[TableRef]:
    """
    Find other BASE TABLEs in schema that have a column named code_column,
    excluding parent and known FK children.
    """
    exclude_set = {(t.schema, t.name) for t in exclude} | {(parent.schema, parent.name)}

    sql = """
        SELECT c.table_schema, c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = %s
          AND t.table_type = 'BASE TABLE'
          AND c.column_name = %s
        ORDER BY c.table_name
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema, code_column))
        rows = cur.fetchall()

    out = []
    for sch, name in rows:
        if (sch, name) in exclude_set:
            continue
        out.append(TableRef(sch, name))
    return out


# ----------------------------
# Counting & deletion helpers
# ----------------------------

def fetch_matching_codes(conn, table: TableRef, code_col: str, patterns: Sequence[str]) -> List[str]:
    clause, params = build_ilike_clause(quote_ident(code_col), patterns)
    sql = f"SELECT {quote_ident(code_col)} FROM {table.qname()} WHERE {clause} ORDER BY {quote_ident(code_col)}"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [r[0] for r in cur.fetchall()]


def count_rows_by_codes(conn, table: TableRef, code_col: str, codes: Sequence[str]) -> int:
    if not codes:
        return 0
    sql = f"SELECT COUNT(*) FROM {table.qname()} WHERE {quote_ident(code_col)} = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (list(codes),))
        return int(cur.fetchone()[0])


def delete_rows_by_codes(conn, table: TableRef, code_col: str, codes: Sequence[str]) -> int:
    if not codes:
        return 0
    sql = f"DELETE FROM {table.qname()} WHERE {quote_ident(code_col)} = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (list(codes),))
        return cur.rowcount


# ----------------------------
# CLI / main
# ----------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    pr = project_root()
    default_dotenv = pr / ".env"
    default_dotenv_str = str(default_dotenv) if default_dotenv.exists() else ""

    p = argparse.ArgumentParser(
        prog="cleanup_test_data.py",
        formatter_class=argparse.RawTextHelpFormatter,
        description="Cleanup test product rows (and their dependencies) from Postgres."
    )

    p.add_argument("--apply", action="store_true", help="Execute deletions (default: dry-run).")
    p.add_argument("--schema", default="public", help="Schema to operate in (default: public).")
    p.add_argument("--table", default=None, help="Main table name (default: auto-detect, prefers 'products').")
    p.add_argument("--code-column", default=None, help="Code column name (default: auto-detect, prefers 'code').")

    p.add_argument("--prefix", action="append", default=None,
                   help="Prefix to match (case-insensitive). Can be repeated.\n"
                        "Example: --prefix INTTEST_")
    p.add_argument("--pattern", action="append", default=None,
                   help="Raw ILIKE pattern(s). Can be repeated.\n"
                        "Note: if your prefix contains '_' and you want literal underscore,\n"
                        "      use an escaped pattern: INTTEST\\_%%\n"
                        "Example: --pattern \"INTTEST\\_%%\"")

    p.add_argument("--dotenv", default=default_dotenv_str,
                   help="Path to .env file to load (default: project .env if present). Use empty to disable.")
    p.add_argument("--override-env", action="store_true", help="Override existing env vars when loading .env.")
    p.add_argument("--verbose", action="store_true", help="More output.")

    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    # Load .env (optional)
    dotenv_path = args.dotenv.strip() if isinstance(args.dotenv, str) else ""
    loaded = load_dotenv_file(dotenv_path or None, override=bool(args.override_env))
    if loaded:
        print(f"Loaded {loaded} env vars from: {dotenv_path}")

    dsn = build_dsn(args)

    # Connect
    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        print("ERROR: cannot connect to Postgres.")
        print(f"  DSN: {dsn}")
        print(f"  {type(e).__name__}: {e}")
        return 2

    conn.autocommit = False

    try:
        schema = args.schema

        # Identify main table + code column
        main_table = pick_main_table(conn, schema, args.table)
        code_col = resolve_code_column(conn, main_table, args.code_column)

        # Build matching patterns
        prefixes = args.prefix if args.prefix else ["INTTEST_"]
        prefix_patterns = patterns_from_prefixes(prefixes)

        raw_patterns = args.pattern if args.pattern else []
        # If user supplies raw patterns, keep them as-is.
        patterns = list(prefix_patterns) + [p for p in raw_patterns if p]

        print(f"Connecting to Postgres with: PG*/DB_* variables (.env supported)")
        # best-effort print connection parts (not password)
        host = os.getenv("DB_HOST") or os.getenv("PGHOST") or "localhost"
        port = os.getenv("DB_PORT") or os.getenv("PGPORT") or "5432"
        db = os.getenv("DB_NAME") or os.getenv("PGDATABASE") or "postgres"
        user = os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
        print(f"  host={host} port={port} db={db} user={user}")
        print(f"Main table: {main_table.schema}.{main_table.name} (code column: {code_col})")

        # Find matching codes in main table
        codes = fetch_matching_codes(conn, main_table, code_col, patterns)
        print(f"Matched codes in main table: {len(codes)}")
        if codes:
            print("Sample codes:")
            for c in codes[:10]:
                print(f"  - {c}")
            if len(codes) > 10:
                print(f"  ... and {len(codes) - 10} more")

        if not codes:
            print("Nothing to delete.")
            conn.rollback()
            return 0

        # FK dependencies referencing the main table
        fks_all = find_fk_deps(conn, main_table)
        # Keep only those that reference the chosen code column
        fks = [fk for fk in fks_all if fk.parent_column == code_col]

        print("\nFK dependencies (child -> parent):")
        if not fks:
            print("  (none)")
        else:
            for fk in fks:
                print(f"  - {fk.child.schema}.{fk.child.name}.{fk.child_column} -> "
                      f"{fk.parent.schema}.{fk.parent.name}.{fk.parent_column}")

        # Distinct child tables; a table can have multiple FK columns, but we only delete by the FK column(s)
        fk_child_tables: Dict[Tuple[str, str], List[str]] = {}
        for fk in fks:
            key = (fk.child.schema, fk.child.name)
            fk_child_tables.setdefault(key, [])
            if fk.child_column not in fk_child_tables[key]:
                fk_child_tables[key].append(fk.child_column)

        fk_table_refs = [TableRef(s, t) for (s, t) in fk_child_tables.keys()]

        # Other tables that have the same "code" column but not in FK list
        other_tables = find_other_code_tables(conn, schema, code_col, main_table, fk_table_refs)

        # Plan counts
        print("\nPlanned deletions (counts):")
        plan: List[Tuple[str, int]] = []

        # 1) FK child tables
        for (sch, tname), cols in sorted(fk_child_tables.items()):
            t = TableRef(sch, tname)
            for col in cols:
                try:
                    cnt = count_rows_by_codes(conn, t, col, codes)
                    plan.append((f"{t.schema}.{t.name} (via FK {col})", cnt))
                except Exception as e:
                    plan.append((f"{t.schema}.{t.name} (via FK {col})", -1))
                    if args.verbose:
                        print(f"  WARN: count failed for {t.schema}.{t.name}.{col}: {e}")

        # 2) Other tables with same code column
        for t in other_tables:
            try:
                cnt = count_rows_by_codes(conn, t, code_col, codes)
                plan.append((f"{t.schema}.{t.name} (by code)", cnt))
            except Exception as e:
                plan.append((f"{t.schema}.{t.name} (by code)", -1))
                if args.verbose:
                    print(f"  WARN: count failed for {t.schema}.{t.name}.{code_col}: {e}")

        # 3) Main table
        plan.append((f"{main_table.schema}.{main_table.name} (main)", len(codes)))

        for label, cnt in plan:
            if cnt >= 0:
                print(f"  - {label}: {cnt}")
            else:
                print(f"  - {label}: (count failed)")

        if not args.apply:
            print("\nDRY-RUN: no changes were made. Use --apply to execute deletions.")
            conn.rollback()
            return 0

        # Execute deletions in a transaction
        print("\nAPPLY: executing deletions...")

        deleted_total = 0

        # 1) Delete from FK child tables first (to satisfy FK constraints)
        for (sch, tname), cols in sorted(fk_child_tables.items()):
            t = TableRef(sch, tname)
            for col in cols:
                deleted = delete_rows_by_codes(conn, t, col, codes)
                deleted_total += deleted
                print(f"  deleted {deleted:>6} from {t.schema}.{t.name} by FK column {col}")

        # 2) Delete from other code tables
        for t in other_tables:
            deleted = delete_rows_by_codes(conn, t, code_col, codes)
            deleted_total += deleted
            print(f"  deleted {deleted:>6} from {t.schema}.{t.name} by code")

        # 3) Delete from main table last
        deleted = delete_rows_by_codes(conn, main_table, code_col, codes)
        deleted_total += deleted
        print(f"  deleted {deleted:>6} from {main_table.schema}.{main_table.name} (main)")

        conn.commit()
        print(f"\nDone. Total deleted rows (across tables): {deleted_total}")

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted. Rolling back.")
        conn.rollback()
        return 130
    except Exception as e:
        print("\nERROR:", str(e))
        conn.rollback()
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
