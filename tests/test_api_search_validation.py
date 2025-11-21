import importlib
import os

import pytest

# Не мешаемся на лимитах в тестах — отключаем limiter
os.environ["RATE_LIMIT_ENABLED"] = "0"

from api import app as app_module  # noqa: E402

importlib.reload(app_module)
app = app_module.app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_simple_search_limit_too_big(client):
    r = client.get("/search?limit=1000")
    assert r.status_code == 400
    data = r.get_json()
    assert data["error"] == "validation_error"


def test_simple_search_bad_max_price(client):
    r = client.get("/search?max_price=abc")
    assert r.status_code == 400
    data = r.get_json()
    assert data["error"] == "validation_error"


def test_simple_search_short_q(client):
    r = client.get("/search?q=a")
    assert r.status_code == 400
    data = r.get_json()
    assert data["error"] == "validation_error"


def test_catalog_search_ok_and_in_stock_flag(client):
    r = client.get("/catalog/search?q=wine&in_stock=true&limit=5")
    assert r.status_code == 200
    assert "items" in r.get_json()


@pytest.mark.parametrize(
    "params",
    [
        {"min_price": "abc"},
        {"max_price": "xyz"},
        {"min_price": "100", "max_price": "abc"},
    ],
)
def test_search_rejects_non_numeric_price_filters(client, params):
    """Поиск должен возвращать 400 при нечисловых min_price/max_price."""
    resp = client.get("/api/v1/products/search", query_string=params)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert "details" in data


def test_search_rejects_min_price_greater_than_max_price(client):
    """min_price > max_price -> 400 и описание ошибки."""
    resp = client.get(
        "/api/v1/products/search",
        query_string={"min_price": "2000", "max_price": "1000"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert "details" in data


@pytest.mark.parametrize("limit", [0, -1, 1000])
def test_search_rejects_invalid_limit(client, limit):
    """limit должен быть в разумных пределах (например, 1..100)."""
    resp = client.get(
        "/api/v1/products/search",
        query_string={"limit": str(limit)},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert "details" in data


@pytest.mark.parametrize("offset", [-1, -10])
def test_search_rejects_negative_offset(client, offset):
    resp = client.get(
        "/api/v1/products/search",
        query_string={"offset": str(offset)},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert "details" in data


@pytest.mark.parametrize("sort", ["foo", "price", "price_up", "name", "1"])
def test_search_rejects_unknown_sort(client, sort):
    """Неизвестное значение sort должно приводить к 400."""
    resp = client.get(
        "/api/v1/products/search",
        query_string={"sort": sort},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "validation_error"
    assert "details" in data


@pytest.mark.parametrize(
    "value, expected_status",
    [
        ("yes", 200),   # валидные булевые строки
        ("no", 200),
        ("maybe", 400), # невалидные значения
        ("2", 400),
    ],
)
def test_search_in_stock_bool_parsing(client, value, expected_status):
    """in_stock должен корректно парситься как bool, а мусор — падать с 400."""
    resp = client.get(
        "/api/v1/products/search",
        query_string={"in_stock": value},
    )
    assert resp.status_code == expected_status
    data = resp.get_json()
    if expected_status == 400:
        assert data["error"] == "validation_error"
        assert "details" in data
    else:
        # для валидных значений валидация не должна ругаться
        assert "error" not in data
