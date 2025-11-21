# tests/integration/test_api_products_search_happy.py
import importlib

import pytest

from api import app as app_module  # noqa: E402
from tests.integration.api_test_utils import _search_products

importlib.reload(app_module)
app = app_module.app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_country_filter(client):
    """
    Поиск по country должен возвращать только товары из указанной страны
    (или подстроку в названии страны).
    """
    items = _search_products(client, country="Южная Африка")

    # Должен быть хотя бы один результат
    assert len(items) > 0

    for item in items:
        assert "country" in item
        assert isinstance(item["country"], str)
        assert "Южная Африка" in item["country"]


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_price_range_filter(client):
    """
    min_price / max_price должны ограничивать диапазон цен в выдаче.
    Проверяем, что все price_final_rub попадают в заданный интервал.
    """
    min_price = 2000
    max_price = 5000

    items = _search_products(
        client,
        min_price=min_price,
        max_price=max_price,
    )

    # Если выдача пустая — ок, главное, чтобы не было нарушений диапазона.
    for item in items:
        price = item.get("price_final_rub")
        assert price is not None
        assert min_price <= price <= max_price


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_in_stock_true_returns_only_items_with_stock(client):
    """
    in_stock=true должен возвращать только товары с положительным stock_free.
    """
    items = _search_products(client, in_stock="true")

    # Может оказаться пустым, если данных нет, но если что-то есть —
    # у всех должен быть положительный stock_free.
    for item in items:
        stock_free = item.get("stock_free")
        # При нашем SQL (WHERE i.stock_free > 0) NULL быть не должно, но проверим на всякий.
        assert stock_free is not None
        assert stock_free > 0


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_limit_is_respected(client):
    """
    Параметр limit должен ограничивать количество возвращаемых товаров.
    """
    limit = 5
    items = _search_products(client, limit=limit)

    # Пустая выдача допустима, но если что-то вернулось — не больше limit.
    assert len(items) <= limit


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_country_and_price_combined_filters(client):
    """
    Комбинация фильтров country + min_price/max_price должна одновременно
    уважать оба ограничения.
    """
    min_price = 2000
    max_price = 5000

    items = _search_products(
        client,
        country="Южная Африка",
        min_price=min_price,
        max_price=max_price,
    )

    # Пустая выдача допустима (зависит от данных),
    # но если что-то есть — все элементы должны удовлетворять обоим условиям.
    for item in items:
        # Проверяем страну
        assert "country" in item
        assert isinstance(item["country"], str)
        assert "Южная Африка" in item["country"]

        # Проверяем диапазон цены
        price = item.get("price_final_rub")
        assert price is not None
        assert min_price <= price <= max_price


@pytest.mark.integration
@pytest.mark.slow
def test_products_search_in_stock_and_price_range_filters(client):
    """
    Комбинация in_stock=true + min_price/max_price:
    все товары должны быть в наличии и в заданном ценовом диапазоне.
    """
    min_price = 1000
    max_price = 10000

    items = _search_products(
        client,
        in_stock="true",
        min_price=min_price,
        max_price=max_price,
    )

    # Пустая выдача допустима, но если что-то вернулось — проверяем инварианты.
    for item in items:
        # Наличие на складе
        stock_free = item.get("stock_free")
        assert stock_free is not None
        assert stock_free > 0

        # Диапазон цены
        price = item.get("price_final_rub")
        assert price is not None
        assert min_price <= price <= max_price
