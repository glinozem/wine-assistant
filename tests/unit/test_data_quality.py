import os
import sys
from datetime import date

import pandas as pd
import pytest

# Добавляем путь к корню репо, чтобы импортировать scripts.*
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.data_quality import DQ_ERRORS_COLUMN, apply_quality_gates


@pytest.mark.unit
def test_apply_quality_gates_all_good():
    """
    Если все строки валидные, bad_df должен быть пустым, а good_df содержать все строки.
    """
    df = pd.DataFrame(
        [
            {
                "code": "ABC123",
                "price_rub": 100.0,
                "price_discount": 90.0,
                "stock_total": 10,
                "reserved": 0,
                "stock_free": 10,
                "abv": 13.5,
                "volume": 0.75,
            },
            {
                "code": "XYZ_999",
                "price_rub": 500.0,
                "price_discount": None,
                "stock_total": 0,
                "reserved": 0,
                "stock_free": 0,
                "abv": 40.0,
                "volume": 0.5,
            },
        ]
    )

    good_df, bad_df = apply_quality_gates(df)

    # good_df содержит все строки, bad_df пустой
    assert len(good_df) == 2
    assert len(bad_df) == 0
    assert DQ_ERRORS_COLUMN in bad_df.columns
    # good_df не обязан содержать колонку с ошибками
    assert DQ_ERRORS_COLUMN not in good_df.columns


@pytest.mark.unit
def test_apply_quality_gates_missing_code_and_negative_price():
    """
    Строка с пустым кодом и отрицательной ценой должна попасть в bad_df
    с ошибками 'missing_code' и 'negative_price_list'.
    """
    df = pd.DataFrame(
        [
            {
                "code": "GOOD1",
                "price_rub": 100.0,
                "price_discount": 90.0,
            },
            {
                "code": "   ",  # пустой/whitespace код
                "price_rub": -10.0,
                "price_discount": None,
            },
        ]
    )

    good_df, bad_df = apply_quality_gates(df)

    # Одна хорошая, одна плохая
    assert len(good_df) == 1
    assert len(bad_df) == 1

    errors = bad_df.iloc[0][DQ_ERRORS_COLUMN]
    assert isinstance(errors, list)
    assert "missing_code" in errors
    assert "negative_price_list" in errors


@pytest.mark.unit
def test_apply_quality_gates_invalid_code_pattern():
    """
    Код, не проходящий паттерн артикула (с пробелами/спецсимволами),
    должен помечаться как 'invalid_code_format'.
    """
    df = pd.DataFrame(
        [
            {
                "code": "OK_123",
                "price_rub": 100.0,
            },
            {
                "code": "A 1",  # пробел, не подходит под паттерн
                "price_rub": 100.0,
            },
        ]
    )

    good_df, bad_df = apply_quality_gates(df)

    # Первая строка должна быть в good_df, вторая — в bad_df
    assert len(good_df) == 1
    assert len(bad_df) == 1

    errors = bad_df.iloc[0][DQ_ERRORS_COLUMN]
    assert "invalid_code_format" in errors


@pytest.mark.unit
def test_apply_quality_gates_invalid_abv_and_volume_and_stock():
    """
    Проверяем несколько типов ошибок одновременно:
      - abv вне диапазона [0, 100];
      - volume <= 0;
      - отрицательные остатки.
    """
    df = pd.DataFrame(
        [
            {
                "code": "GOOD_OK",
                "price_rub": 100.0,
                "abv": 13.5,
                "volume": 0.75,
                "stock_total": 10,
                "reserved": 0,
                "stock_free": 10,
            },
            {
                "code": "BAD_1",
                "price_rub": 100.0,
                "abv": 150.0,   # слишком большой градус
                "volume": 0.0,  # нулевой объём
                "stock_total": -1,
                "reserved": -2,
                "stock_free": -3,
            },
        ]
    )

    good_df, bad_df = apply_quality_gates(df)

    assert len(good_df) == 1
    assert len(bad_df) == 1

    errors = bad_df.iloc[0][DQ_ERRORS_COLUMN]
    assert "invalid_abv_range" in errors
    assert "invalid_volume" in errors
    assert "negative_stock_total" in errors
    assert "negative_reserved" in errors
    assert "negative_stock_free" in errors
