import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg2


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str


def _get_db_config() -> DbConfig:
    # Support the env naming already used across this repo (db container and local dev).
    # Fallbacks are aligned with docker-compose defaults.
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "wine_db"))
    user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
    password = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres"))

    return DbConfig(host=host, port=port, name=name, user=user, password=password)


def _connect(cfg: DbConfig):
    return psycopg2.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.name,
        user=cfg.user,
        password=cfg.password,
    )


def _get_anchor_effective_from(cur) -> datetime:
    cur.execute("select max(effective_from) from public.product_prices")
    ts = cur.fetchone()[0]
    if ts is None:
        # This case is not expected in your current setup (you already have price history).
        # But keep a deterministic fallback so the script is usable in new DBs.
        # NOTE: if product_prices is partitioned by effective_from and partitions are limited,
        # you may need to adjust this anchor to match an existing partition.
        return datetime.now(tz=timezone.utc)
    # Ensure tz-aware for consistent printing.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


SQL_FIX_PRODUCTS = """
update public.products
set price_final_rub = price_list_rub
where price_final_rub is null
  and price_list_rub is not null
"""

SQL_COUNT_BAD_PRODUCTS = """
select count(*)
from public.products
where price_list_rub is not null
  and price_final_rub is null
"""

SQL_COUNT_MISSING_CURRENT = """
select count(*)
from public.products p
left join public.product_prices pp
  on pp.code = p.code
 and pp.effective_to is null
where pp.code is null
"""

# Idempotent insert for "current" prices.
SQL_REOPEN_ANCHOR_ROWS = """
with anchor as (
  select %s::timestamptz as ts
), missing as (
  select
    p.code,
    coalesce(p.price_final_rub, p.price_list_rub) as price_rub
  from public.products p
  left join public.product_prices pp
    on pp.code = p.code
   and pp.effective_to is null
  where pp.code is null
)
update public.product_prices pp
set
  effective_to = null,
  price_rub = m.price_rub
from anchor a, missing m
where pp.code = m.code
  and pp.effective_from = a.ts
  and pp.effective_to is not null
  and m.price_rub is not null
"""


SQL_INSERT_MISSING_CURRENT = """
with anchor as (
  select %s::timestamptz as ts
), missing as (
  select
    p.code,
    coalesce(p.price_final_rub, p.price_list_rub) as price_rub
  from public.products p
  left join public.product_prices pp
    on pp.code = p.code
   and pp.effective_to is null
  where pp.code is null
)
insert into public.product_prices (code, price_rub, effective_from, effective_to)
select m.code, m.price_rub, a.ts, null
from missing m
cross join anchor a
where m.price_rub is not null
  and not exists (
    select 1
    from public.product_prices pp2
    where pp2.code = m.code
      and pp2.effective_to is null
  )
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill current price rows in public.product_prices and fix NULL price_final_rub. "
            "Safe to run multiple times (idempotent)."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print counts; do not modify data (default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to DB",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    cfg = _get_db_config()

    with _connect(cfg) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            anchor = _get_anchor_effective_from(cur)

            # Pre-checks
            cur.execute(SQL_COUNT_BAD_PRODUCTS)
            bad_before = int(cur.fetchone()[0])
            cur.execute(SQL_COUNT_MISSING_CURRENT)
            missing_before = int(cur.fetchone()[0])

            if dry_run:
                print(f"[dry-run] anchor_effective_from={anchor.isoformat()}")
                print(f"[dry-run] products with price_list_rub != NULL and price_final_rub == NULL: {bad_before}")
                print(f"[dry-run] products missing current price row (effective_to is NULL): {missing_before}")
                return 0

            # Apply fixes
            cur.execute(SQL_FIX_PRODUCTS)
            fixed_products = cur.rowcount

            cur.execute(SQL_REOPEN_ANCHOR_ROWS, (anchor,))
            reopened_prices = cur.rowcount

            cur.execute(SQL_INSERT_MISSING_CURRENT, (anchor,))
            inserted_prices = cur.rowcount

            # Post-checks
            cur.execute(SQL_COUNT_BAD_PRODUCTS)
            bad_after = int(cur.fetchone()[0])
            cur.execute(SQL_COUNT_MISSING_CURRENT)
            missing_after = int(cur.fetchone()[0])

            conn.commit()

            print(f"✅ products.price_final_rub backfill: updated_rows={fixed_products}")
            print(f"✅ product_prices current rows backfill: inserted_rows={inserted_prices} (anchor={anchor.isoformat()})")
            print(f"[check] remaining bad products: {bad_after}")
            print(f"[check] remaining missing current prices: {missing_after}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
