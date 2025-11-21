# scripts/load_csv.py
from __future__ import annotations

import argparse
import logging
import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import openpyxl  # чтение значения скидки из фиксированной ячейки (например, S5)
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Date extraction module for automatic date parsing (Issue #81)
from scripts.date_extraction import get_effective_date

# Idempotency module for preventing duplicate imports (Issue #80)
from scripts.idempotency import (
    check_file_exists,
    compute_file_sha256,
    create_envelope,
    create_price_list_entry,
    update_envelope_status,
)
from scripts.load_utils import (
    COLMAP,
    _canonicalize_headers,
    _csv_read,
    _excel_read,
    _get_discount_from_cell,
    _norm,
    _norm_key,
    _to_float,
    _to_int,
    get_conn,
    read_any,
    upsert_records,
)

load_dotenv()


# =========================
# CLI
# =========================
def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="Путь к CSV")
    g.add_argument("--excel", help="Путь к Excel (xlsx/xls)")
    p.add_argument("--sep", help="Разделитель CSV (если нужен)")
    p.add_argument("--sheet", help="Имя/индекс листа Excel (по умолчанию 0)")
    p.add_argument(
        "--header", type=int, help="Номер строки заголовка (0-based). Если не указан — авто-поиск"
    )
    p.add_argument(
        "--asof",
        help="Дата 'среза' (YYYY-MM-DD) для истории цен и остатков. "
        "Если не указана — автоматически извлекается из Excel ячейки или имени файла. "
        "Fallback: сегодняшняя дата.",
    )
    p.add_argument(
        "--date-cell",
        default="A1",
        help="Ячейка Excel для извлечения даты (по умолчанию A1). "
        "Также проверяются B1, A2, B2 как fallback.",
    )
    p.add_argument(
        "--discount-cell",
        default=os.environ.get("DISCOUNT_CELL", "S5"),
        help="Адрес ячейки со скидкой (по умолчанию S5). Пример: T3",
    )
    p.add_argument(
        "--prefer-discount-cell",
        action="store_true",
        help="Если указан флаг — финальная цена рассчитывается по скидке из ячейки даже при наличии колонки 'Цена со скидкой'",
    )
    args = p.parse_args()

    path = args.csv or args.excel

    # ==========================
    # Automatic date extraction (Issue #81)
    # ==========================
    # Parse --asof if provided
    asof_override: Optional[date] = None
    if args.asof:
        try:
            asof_override = datetime.strptime(args.asof, "%Y-%m-%d").date()
        except ValueError as e:
            print(f"Error: Invalid date format for --asof. Expected YYYY-MM-DD, got: {args.asof}")
            raise

    # Get effective date (auto-extract or use override)
    try:
        asof_dt = get_effective_date(
            file_path=path, asof_override=asof_override, date_cell=args.date_cell
        )
        print(
            f"[date] Effective date: {asof_dt} (source: "
            f"{'--asof override' if asof_override else 'auto-extracted'})"
        )
    except ValueError as e:
        print(f"Error: {e}")
        raise

    # ==========================
    # Idempotency check (Issue #80)
    # ==========================
    logger = logging.getLogger(__name__)

    # Compute SHA256 hash of the file
    file_hash = compute_file_sha256(path)
    file_size = os.path.getsize(path)
    file_name = os.path.basename(path)

    logger.info(
        "File fingerprint computed",
        extra={
            "file_name": file_name,
            "file_hash": file_hash[:16] + "...",
            "file_size_bytes": file_size,
        },
    )

    # Check if file already exists in database
    conn = get_conn()
    try:
        existing = check_file_exists(conn, file_hash)

        if existing:
            logger.warning(
                ">> SKIP: File already imported",
                extra={
                    "envelope_id": existing["envelope_id"],
                    "file_name": existing["file_name"],
                    "status": existing["status"],
                    "upload_timestamp": existing["upload_timestamp"].isoformat(),
                    "rows_inserted": existing["rows_inserted"],
                },
            )
            print(f"\n>> SKIP: File already imported")
            print(f"   Envelope ID: {existing['envelope_id']}")
            print(f"   Status: {existing['status']}")
            print(f"   Uploaded: {existing['upload_timestamp']}")
            print(f"   Rows inserted: {existing['rows_inserted']}")
            print(f"\n   This file has already been processed. No action taken.")
            conn.close()
            return  # Exit early - file already processed

        # File is new - create envelope
        envelope_id = create_envelope(
            conn,
            file_name=file_name,
            file_hash=file_hash,
            file_path=path,
            file_size_bytes=file_size,
        )

        logger.info("Created new envelope for import", extra={"envelope_id": str(envelope_id)})

    except Exception as e:
        logger.error(f"Error checking file idempotency: {e}", exc_info=True)
        conn.close()
        raise

    # Continue with normal import process
    df = read_any(path, sep=args.sep, sheet=args.sheet, header=args.header)

    # Получим скидку из шапки и/или из S5, выберем согласно приоритету
    disc_hdr = df.attrs.get("discount_pct_header")  # возможно, извлекли из второй строки заголовка
    # sheet для S5
    sh = args.sheet
    try:
        sh = int(sh) if sh not in (None, "") else 0
    except ValueError:
        sh = sh if sh not in (None, "") else 0
    disc_cell = _get_discount_from_cell(args.excel, sh, args.discount_cell) if args.excel else None

    prefer_s5 = args.prefer_discount_cell or (os.environ.get("PREFER_S5") in ("1", "true", "True"))
    if prefer_s5:
        discount = disc_cell if disc_cell is not None else disc_hdr
    else:
        discount = disc_hdr if disc_hdr is not None else disc_cell

    df.attrs["discount_pct_cell"] = disc_cell
    df.attrs["discount_pct"] = discount
    print(
        f"[discount] header={disc_hdr}  cell({args.discount_cell})={disc_cell}  -> used={discount}"
    )

    # Отбираем только нужные поля
    keep = {
        "code",
        "title_ru",
        "producer",
        "country",
        "region",
        "grapes",
        "abv",
        "pack",
        "volume",
        "price_rub",
        "price_discount",
        "stock_total",
        "reserved",
        "stock_free",
    }
    have = [c for c in df.columns if c in keep]
    have = list(dict.fromkeys(have))  # удалим дубликаты имён, сохраняя порядок

    if "code" not in have:
        raise ValueError("В данных отсутствует колонка с кодом (code).")

    df = df[have].copy()
    df = df[df["code"].astype(str).str.len() > 0]  # выкинем строки без кода

    # только «похожие на артикул»: без пробелов, латиница/цифры/_, -, длина ≥ 3
    pattern = r"^[A-Za-z0-9][A-Za-z0-9_-]{2,}$"
    df = df[df["code"].str.match(pattern, na=False)]

    # выкинем строки, где вообще нет ни прайса, ни финальной из файла
    if "price_rub" in df.columns:
        df["price_rub_num"] = df["price_rub"].map(_to_float)
    if "price_discount" in df.columns:
        df["price_discount_num"] = df["price_discount"].map(_to_float)
    if "price_rub_num" in df.columns and "price_discount_num" in df.columns:
        df = df[df["price_rub_num"].notna() | df["price_discount_num"].notna()]
    df = df.drop(columns=[c for c in ("price_rub_num", "price_discount_num") if c in df.columns])

    # ==========================
    # Import data
    # ==========================
    try:
        rows_before = len(df)
        upsert_records(df, asof_dt)

        # Update envelope status to success
        update_envelope_status(
            conn,
            envelope_id,
            status="success",
            rows_inserted=rows_before,  # All rows processed
            rows_updated=0,
            rows_failed=0,
        )

        # Create price_list entry linking envelope to effective date
        price_list_id = create_price_list_entry(
            conn,
            envelope_id,
            effective_date=asof_dt if isinstance(asof_dt, date) else asof_dt.date(),
            file_path=path,
            discount_percent=discount,
        )

        logger.info(
            "[OK] Import completed successfully",
            extra={
                "envelope_id": str(envelope_id),
                "price_list_id": str(price_list_id),
                "rows_processed": rows_before,
                "effective_date": asof_dt.isoformat()
                if isinstance(asof_dt, date)
                else asof_dt.date().isoformat(),
            },
        )

        print(f"\n[OK] Import completed successfully")
        print(f"   Envelope ID: {envelope_id}")
        print(f"   Rows processed: {rows_before}")
        print(f"   Effective date: {asof_dt}")

    except Exception as e:
        # Update envelope status to failed
        update_envelope_status(
            conn,
            envelope_id,
            status="failed",
            rows_inserted=0,
            rows_updated=0,
            rows_failed=0,
            error_message=str(e),
        )

        logger.error(
            "[ERROR] Import failed",
            extra={"envelope_id": str(envelope_id), "error": str(e)},
            exc_info=True,
        )

        conn.close()
        raise

    conn.close()


if __name__ == "__main__":
    main()
