# scripts/load_csv.py
from __future__ import annotations

"""
CLI entrypoint for importing a price list file (CSV or Excel) into the database.

Responsibilities:
  * parse CLI arguments (--csv/--excel, --asof, --date-cell, --discount-cell, --prefer-discount-cell);
  * compute file hash and enforce idempotency (Issue #80);
  * extract effective date from filename or Excel cell (Issue #81);
  * read and normalize tabular data via scripts.load_utils.read_any();
  * determine discount percentage from header / fixed cell and store it in df.attrs;
  * call upsert_records() to write products / prices / inventory into the DB;
  * update envelope and price_list metadata in the idempotency tables.
  * опционально сохраняет некорректные строки прайса в таблицу карантина (price_list_quarantine).
"""

import argparse
import logging
import os
from datetime import date, datetime
from typing import Dict, Optional

from dotenv import load_dotenv

# Low-level ETL helpers
from scripts.data_quality import (
    DQ_ERRORS_COLUMN,
    apply_quality_gates,
    persist_quarantine_rows,
)

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
    _get_discount_from_cell,
    _to_float,
    get_conn,
    read_any,
    upsert_records,
)

load_dotenv()
logger = logging.getLogger(__name__)


# =========================
# CLI
# =========================
def build_arg_parser() -> argparse.ArgumentParser:
    """
    Build argument parser for the price import CLI.
    """
    p = argparse.ArgumentParser(
        description=(
            "Импорт прайс-листа (CSV/Excel) в БД. "
            "Отвечает за идемпотентность, определение даты среза и выбор скидки."
        )
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--csv",
        help="Путь к CSV-файлу прайс-листа.",
    )
    g.add_argument(
        "--excel",
        help="Путь к Excel-файлу прайс-листа (xlsx/xls).",
    )
    p.add_argument(
        "--sep",
        help="Разделитель CSV (если нужен; по умолчанию авто-детект).",
    )
    p.add_argument(
        "--sheet",
        help="Имя/индекс листа Excel (по умолчанию 0).",
    )
    p.add_argument(
        "--header",
        type=int,
        help=(
            "Номер строки заголовка (0-based). "
            "Если не указан — будет выполнен авто-поиск по ключам 'Код'/'code'/'Артикул'."
        ),
    )
    p.add_argument(
        "--asof",
        help=(
            "Дата 'среза' (YYYY-MM-DD) для истории цен и остатков. "
            "Если не указана — автоматически извлекается из Excel-ячейки или имени файла "
            "(см. scripts.date_extraction.get_effective_date). "
            "Fallback: сегодняшняя дата."
        ),
    )
    p.add_argument(
        "--date-cell",
        default="A1",
        help=(
            "Ячейка Excel для извлечения даты (по умолчанию A1). "
            "Также проверяются B1, A2, B2 как fallback."
        ),
    )
    p.add_argument(
        "--discount-cell",
        default=os.environ.get("DISCOUNT_CELL", "S5"),
        help=(
            "Адрес ячейки со скидкой (по умолчанию S5, можно переопределить через DISCOUNT_CELL). "
            "Пример: T3."
        ),
    )
    p.add_argument(
        "--prefer-discount-cell",
        action="store_true",
        help=(
            "Если указан флаг — приоритет за скидкой из фиксированной ячейки "
            "(--discount-cell) даже при наличии колонки 'Цена со скидкой'. "
            "Флаг имеет приоритет над переменной окружения PREFER_S5."
        ),
    )
    return p


def main(argv: Optional[list] = None) -> None:
    """
    CLI entrypoint.

    Args:
        argv: Список аргументов командной строки (без имени скрипта).
              Если None — используются sys.argv[1:].
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    path = args.csv or args.excel

    # ==========================
    # Automatic date extraction (Issue #81)
    # ==========================
    # Parse --asof if provided
    asof_override: Optional[date] = None
    if args.asof:
        try:
            asof_override = datetime.strptime(args.asof, "%Y-%m-%d").date()
        except ValueError:
            msg = f"Invalid date format for --asof. Expected YYYY-MM-DD, got: {args.asof}"
            print(f"Error: {msg}")
            raise ValueError(msg)

    # Get effective date (auto-extract or use override)
    try:
        asof_dt = get_effective_date(
            file_path=path,
            asof_override=asof_override,
            date_cell=args.date_cell,
        )
        print(
            "[date] Effective date: "
            f"{asof_dt} (source: "
            f"{'--asof override' if asof_override else 'auto-extracted'})"
        )
    except ValueError as e:
        print(f"Error: {e}")
        raise

    # ==========================
    # Idempotency check (Issue #80)
    # ==========================
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

    conn = get_conn()

    try:
        existing = check_file_exists(conn, file_hash)

        if existing:
            # File already processed: log and exit early
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
            print("\n>> SKIP: File already imported")
            print(f"   Envelope ID: {existing['envelope_id']}")
            print(f"   Status: {existing['status']}")
            print(f"   Uploaded: {existing['upload_timestamp']}")
            print(f"   Rows inserted: {existing['rows_inserted']}")
            print("\n   This file has already been processed. No action taken.")
            conn.close()
            return

        # File is new - create envelope
        envelope_id = create_envelope(
            conn,
            file_name=file_name,
            file_hash=file_hash,
            file_path=path,
            file_size_bytes=file_size,
        )

        logger.info(
            "Created new envelope for import",
            extra={"envelope_id": str(envelope_id)},
        )

    except Exception:
        logger.error(
            "Error checking file idempotency",
            extra={"file_name": file_name, "file_hash": file_hash[:16] + "..."},
            exc_info=True,
        )
        conn.close()
        raise

    # ==========================
    # Read and normalize data
    # ==========================
    df = read_any(path, sep=args.sep, sheet=args.sheet, header=args.header)

    # Получим скидку из шапки и/или из S5, выберем согласно приоритету
    disc_hdr = df.attrs.get(
        "discount_pct_header"
    )  # возможно, извлекли из второй строки заголовка

    # sheet для S5
    sh = args.sheet
    try:
        sh = int(sh) if sh not in (None, "") else 0
    except ValueError:
        sh = sh if sh not in (None, "") else 0

    disc_cell = _get_discount_from_cell(args.excel, sh, args.discount_cell) if args.excel else None

    # CLI-флаг имеет приоритет над окружением
    prefer_s5_cli = bool(args.prefer_discount_cell)
    prefer_s5_env = os.environ.get("PREFER_S5") in ("1", "true", "True")
    prefer_s5 = prefer_s5_cli or prefer_s5_env

    if prefer_s5:
        discount = disc_cell if disc_cell is not None else disc_hdr
    else:
        discount = disc_hdr if disc_hdr is not None else disc_cell

    # сохраняем все варианты в attrs, чтобы upsert_records()
    # мог опираться на них при расчёте цен
    df.attrs["discount_pct_header"] = disc_hdr
    df.attrs["discount_pct_cell"] = disc_cell
    df.attrs["discount_pct"] = discount
    df.attrs["prefer_discount_cell"] = prefer_s5

    print(
        "[discount] "
        f"header={disc_hdr}  cell({args.discount_cell})={disc_cell}  "
        f"prefer_s5_cli={prefer_s5_cli} prefer_s5_env={prefer_s5_env}  -> used={discount}"
    )

    # Отбираем только нужные поля
    keep = {
        "code",
        "title_ru",
        "producer",
        "country",
        "region",
        "color",
        "style",
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

    # ==========================
    # Data quality gates (Issue #83)
    # ==========================
    good_df, bad_df = apply_quality_gates(df)

    if not bad_df.empty:
        total_bad = len(bad_df)
        error_counts: Dict[str, int] = {}
        for errs in bad_df[DQ_ERRORS_COLUMN]:
            for code in errs:
                error_counts[code] = error_counts.get(code, 0) + 1

        logger.warning(
            "[dq] Some rows failed data quality checks; they will be skipped from import",
            extra={
                "rows_failed": total_bad,
                "dq_error_counts": error_counts,
            },
        )
        print(
            f"[dq] {total_bad} row(s) failed data quality checks and will be skipped. "
            "See logs for aggregated error statistics."
        )

    # дальше в импорт идём только с good_df
    df = good_df

    # ==========================
    # Import data
    # ==========================
    try:
        rows_good = len(df)

        # сначала сохраняем плохие строки в карантин (если есть)
        rows_failed = persist_quarantine_rows(conn, envelope_id, bad_df)

        # затем импортируем только хорошие строки
        upsert_records(df, asof_dt)

        # Update envelope status to success
        update_envelope_status(
            conn,
            envelope_id,
            status="success",
            rows_inserted=rows_good,
            rows_updated=0,
            rows_failed=rows_failed,
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
                "rows_processed": rows_good,
                "rows_failed": rows_failed,
                "effective_date": asof_dt.isoformat()
                if isinstance(asof_dt, date)
                else asof_dt.date().isoformat(),
            },
        )

        print("\n[OK] Import completed successfully")
        print(f"   Envelope ID: {envelope_id}")
        print(f"   Rows processed (good): {rows_good}")
        print(f"   Rows failed (quarantine): {rows_failed}")
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
