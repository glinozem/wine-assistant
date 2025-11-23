# scripts/data_quality.py
from __future__ import annotations

"""
Data quality utilities for imported price list data.

Responsibilities:
    * validate individual rows (код, цены, остатки, abv, объём);
    * split incoming DataFrame into "good" and "bad" rows;
    * attach machine-readable error codes to "bad" rows;
    * optionally persist invalid rows into a quarantine table.

Quality gates themselves are pure Pandas operations; only
`persist_quarantine_rows()` выполняет запись в БД.
"""

import json
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import pandas as pd

from scripts.load_utils import _to_float, _to_int

DQ_ERRORS_COLUMN = "__dq_errors"

# Тот же паттерн для кода, что и в load_csv: "похож на артикул"
CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,}$")

# [INTERNAL] reserved for future use
@dataclass(frozen=True)
class DataQualityIssue:
    """
    [PUBLIC API]:
      validate_row, apply_quality_gates, persist_quarantine_rows
    [INTERNAL]:
      _is_empty, CODE_PATTERN, DQ_ERRORS_COLUMN
    """
    row_index: int
    code: str
    message: str


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def validate_row(row: pd.Series) -> List[str]:
    """
    Run data quality checks on a single row and return a list of error codes.

    Error codes (не полный список, можно расширять):
        * "missing_code"         — пустой или отсутствующий код.
        * "invalid_code_format"  — код не соответствует артикулу (см. CODE_PATTERN).
        * "missing_price"        — нет ни одной цены (ни прайс, ни финальная).
        * "negative_price_list"  — price_rub < 0.
        * "negative_price_discount" — price_discount < 0.
        * "negative_stock_total", "negative_reserved", "negative_stock_free".
        * "invalid_abv_range"    — abv < 0 или > 100.
        * "invalid_volume"       — volume <= 0.
    """
    errors: List[str] = []

    # --- Код ---
    code = row.get("code")
    if _is_empty(code):
        errors.append("missing_code")
    else:
        code_str = str(code).strip()
        if not CODE_PATTERN.match(code_str):
            errors.append("invalid_code_format")

    # --- Цены ---
    price_rub = _to_float(row.get("price_rub")) if "price_rub" in row else None
    price_disc = _to_float(row.get("price_discount")) if "price_discount" in row else None

    if price_rub is None and price_disc is None:
        # если есть хотя бы одна из колонок, но обе пустые/невалидные
        if "price_rub" in row or "price_discount" in row:
            errors.append("missing_price")
    else:
        if price_rub is not None and price_rub < 0:
            errors.append("negative_price_list")
        if price_disc is not None and price_disc < 0:
            errors.append("negative_price_discount")

    # --- Остатки ---
    for col, err_code in (
        ("stock_total", "negative_stock_total"),
        ("reserved", "negative_reserved"),
        ("stock_free", "negative_stock_free"),
    ):
        if col in row:
            v = _to_int(row.get(col))
            if v is not None and v < 0:
                errors.append(err_code)

    # --- ABV ---
    if "abv" in row:
        abv = _to_float(row.get("abv"))
        if abv is not None and not (0.0 <= abv <= 100.0):
            errors.append("invalid_abv_range")

    # --- Объём ---
    if "volume" in row:
        vol = _to_float(row.get("volume"))
        if vol is not None and vol <= 0.0:
            errors.append("invalid_volume")

    return errors


def apply_quality_gates(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split DataFrame into "good" and "bad" rows according to data quality rules.

    Returns:
        good_df, bad_df

    Where:
        * good_df — копия исходных строк без ошибок;
        * bad_df  — копия строк с ошибками + колонка DQ_ERRORS_COLUMN
                    (список строковых error code'ов для каждой строки).
    """
    if df.empty:
        # Пустой вход — оба фрейма пустые с одинаковыми колонками
        good_empty = df.copy()
        bad_empty = df.copy()
        if DQ_ERRORS_COLUMN not in bad_empty.columns:
            bad_empty[DQ_ERRORS_COLUMN] = []
        return good_empty, bad_empty

    good_indices: List[int] = []
    bad_indices: List[int] = []
    row_errors: List[List[str]] = []

    # Проходим по строкам и собираем ошибки
    for idx, row in df.iterrows():
        errs = validate_row(row)
        if errs:
            bad_indices.append(idx)
            row_errors.append(errs)
        else:
            good_indices.append(idx)

    # good_df
    good_df = df.loc[good_indices].copy() if good_indices else df.head(0).copy()

    # bad_df
    if bad_indices:
        bad_df = df.loc[bad_indices].copy()
        bad_df[DQ_ERRORS_COLUMN] = row_errors
    else:
        bad_df = df.head(0).copy()
        bad_df[DQ_ERRORS_COLUMN] = []

    return good_df, bad_df


def persist_quarantine_rows(
    conn,
    envelope_id,
    bad_df: pd.DataFrame,
    dq_errors_column: str = DQ_ERRORS_COLUMN,
) -> int:
    """
    Сохраняет некорректные строки из bad_df в таблицу price_list_quarantine.

    - Каждая строка сохраняется в raw_row (jsonb) без служебной колонки dq_errors_column.
    - Код (если есть) пишется отдельно в колонку code.
    - Список ошибок пишется в dq_errors::text[].
    - Возвращает количество записанных строк.
    """
    if bad_df is None or bad_df.empty:
        return 0

    rows = []
    for _, row in bad_df.iterrows():
        raw = row.to_dict()

        # отдельно забираем dq_errors
        errors_val = raw.pop(dq_errors_column, None)

        if errors_val is None:
            errors: Iterable[str] = []
        elif isinstance(errors_val, str):
            errors = [errors_val]
        else:
            try:
                errors = list(errors_val)
            except TypeError:
                errors = [str(errors_val)]

        code_val = raw.get("code")

        rows.append(
            (
                envelope_id,
                code_val,
                json.dumps(raw, ensure_ascii=False),
                errors,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO price_list_quarantine (envelope_id, code, raw_row, dq_errors)
            VALUES (%s, %s, %s::jsonb, %s::text[])
            """,
            rows,
        )

    conn.commit()
    return len(rows)
