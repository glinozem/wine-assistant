# tests/unit/test_schemas.py
from datetime import date

import pytest
from pydantic import ValidationError

from api.schemas import (
    CatalogSearchParams,
    InventoryHistoryParams,
    PriceHistoryParams,
    SimpleSearchParams,
)


def test_simple_search_q_trim_and_min_length_ok():
    """
    q должен триммиться и проходить, если длина >= 2.
    """
    params = SimpleSearchParams.model_validate({"q": "  wine  ", "limit": 5})
    assert params.q == "wine"
    assert params.limit == 5


def test_simple_search_q_too_short_raises_validation_error():
    """
    q длиной 1 символ должен падать с ValidationError.
    """
    with pytest.raises(ValidationError) as excinfo:
        SimpleSearchParams.model_validate({"q": "a"})

    msg = str(excinfo.value)
    assert "at least 2 characters" in msg


def test_catalog_search_price_range_ok_when_min_le_max():
    """
    min_price <= max_price — валидно.
    """
    params = CatalogSearchParams.model_validate({"min_price": 10, "max_price": 20})
    assert params.min_price == 10
    assert params.max_price == 20


def test_catalog_search_price_range_invalid_when_min_gt_max():
    """
    min_price > max_price — должно вызывать ValidationError.
    """
    with pytest.raises(ValidationError) as excinfo:
        CatalogSearchParams.model_validate({"min_price": 20, "max_price": 10})

    msg = str(excinfo.value)
    assert "min_price must be <= max_price" in msg


def test_price_history_date_range_aliases_and_validation_ok():
    """
    PriceHistoryParams должен правильно парсить алиасы from/to и валидный диапазон.
    """
    params = PriceHistoryParams.model_validate(
        {
            "from": "2025-01-01",
            "to": "2025-01-10",
            "limit": 10,
            "offset": 0,
        }
    )
    assert isinstance(params.dt_from, date)
    assert isinstance(params.dt_to, date)
    assert params.dt_from == date(2025, 1, 1)
    assert params.dt_to == date(2025, 1, 10)


def test_price_history_date_range_invalid_when_from_gt_to():
    """
    from > to должен приводить к ValidationError в PriceHistoryParams.
    """
    with pytest.raises(ValidationError) as excinfo:
        PriceHistoryParams.model_validate(
            {
                "from": "2025-02-01",
                "to": "2025-01-01",
            }
        )

    msg = str(excinfo.value)
    assert "'from' must be <= 'to'" in msg


def test_inventory_history_uses_same_date_range_validation():
    """
    InventoryHistoryParams должен наследовать ту же логику проверки диапазона.
    """
    with pytest.raises(ValidationError):
        InventoryHistoryParams.model_validate(
            {
                "from": "2025-02-01",
                "to": "2025-01-01",
            }
        )
