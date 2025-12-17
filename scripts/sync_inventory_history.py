#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

# ────────────────────────────────────────────────────────────────
# Настраиваем PYTHONPATH, чтобы можно было импортировать api.app
# ────────────────────────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api.app import _close_conn_safely, db_connect, db_query  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Синхронизировать текущие остатки из public.inventory "
            "в public.inventory_history (один снимок на дату)."
        )
    )
    parser.add_argument(
        "--as-of",
        help=(
            "Дата/время снимка в ISO-формате (например, 2025-02-15 или "
            "2025-02-15T10:30:00). По умолчанию: текущее время в UTC."
        ),
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только посчитать, сколько строк будет вставлено, БД не изменять.",
    )
    return parser.parse_args()


def _parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    # Пробуем ISO-формат: дата или дата+время
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        # если без таймзоны — считаем, что это UTC
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def sync_inventory_history(as_of: datetime, dry_run: bool = False) -> int:
    """
    Копирует текущие остатки из public.inventory в public.inventory_history.

    - Берём только SKU, где stock_total или stock_free != 0.
    - reserved вычисляем как (stock_total - stock_free, минимум 0).
    - Для каждого code вставляем строку только если
      в inventory_history ещё нет записи с таким code и as_of::date.
    """

    conn, err = db_connect()
    if err or not conn:
        raise SystemExit(f"❌ Не удалось подключиться к БД: {err}")

    try:
        as_of_date = as_of.date()

        params: dict[str, Any] = {
            "as_of": as_of,
            "as_of_date": as_of_date,
        }

        # Запрос для dry-run: считаем, сколько строк будет вставлено
        count_sql = """
            SELECT COUNT(*) AS cnt
            FROM public.inventory i
            WHERE
              (COALESCE(i.stock_total, 0) <> 0 OR COALESCE(i.stock_free, 0) <> 0)
              AND NOT EXISTS (
                SELECT 1
                FROM public.inventory_history h
                WHERE h.code = i.code
                  AND h.as_of::date = %(as_of_date)s
              )
        """

        rows = db_query(conn, count_sql, params)
        to_insert = int(rows[0]["cnt"]) if rows else 0

        if dry_run:
            print(
                f"[dry-run] as_of={as_of.isoformat()} — "
                f"будет вставлено строк: {to_insert}"
            )
            return to_insert

        if to_insert == 0:
            print(
                f"as_of={as_of.isoformat()} — новых записей нет, "
                "inventory_history уже синхронизирован на эту дату."
            )
            return 0

        insert_sql = """
            INSERT INTO public.inventory_history (
                code,
                stock_total,
                reserved,
                stock_free,
                as_of
            )
            SELECT
                i.code,
                COALESCE(i.stock_total, 0) AS stock_total,
                GREATEST(
                    COALESCE(i.stock_total, 0) - COALESCE(i.stock_free, 0),
                    0
                )                           AS reserved,
                COALESCE(i.stock_free, 0)   AS stock_free,
                %(as_of)s                   AS as_of
            FROM public.inventory i
            WHERE
              (COALESCE(i.stock_total, 0) <> 0 OR COALESCE(i.stock_free, 0) <> 0)
              AND NOT EXISTS (
                SELECT 1
                FROM public.inventory_history h
                WHERE h.code = i.code
                  AND h.as_of::date = %(as_of_date)s
              )
        """

        cursor = conn.cursor()
        cursor.execute(insert_sql, params)
        inserted = cursor.rowcount or 0
        conn.commit()

        print(
            f"✅ Вставлено {inserted} записей в public.inventory_history "
            f"для as_of={as_of.isoformat()}"
        )
        return inserted
    finally:
        _close_conn_safely(conn)


def main() -> None:
    args = parse_args()
    as_of = _parse_as_of(args.as_of)
    sync_inventory_history(as_of=as_of, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
