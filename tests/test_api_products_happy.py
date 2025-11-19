import importlib
from datetime import date, datetime

import pytest


def _norm_params(p):
    """Преобразуем date/datetime -> 'YYYY-MM-DD' для стабильных ассертів."""
    out = []
    for x in p:
        if isinstance(x, datetime):
            out.append(x.date().isoformat())
        elif isinstance(x, date):
            out.append(x.isoformat())
        else:
            out.append(x)
    return tuple(out)

# --- вспомогательный "коннект" ---
class _DummyConn:
    def close(self) -> None:  # соответствует ожидаемому интерфейсу
        pass

@pytest.fixture
def app_with_key_and_mocks(monkeypatch):
    # Включаем ключ, чтобы проходили защищённые роуты
    monkeypatch.setenv("API_KEY", "test-key")

    # Импортируем и перезагружаем модуль, чтобы подтянулись env-переменные
    from api import app as app_module
    importlib.reload(app_module)

    # Хранилище последних SQL/params — чтобы проверки делать в тестах
    calls = {"last_sql": None, "last_params": None}

    # Мокаем db_connect: возвращает "живой" коннект и None-ошибку
    def _fake_db_connect():
        return _DummyConn(), None

    monkeypatch.setattr(app_module, "db_connect", _fake_db_connect, raising=True)

    # Мокаем db_query: пишем последний SQL и параметры, возвращаем заранее «подложенные» строки
    def _fake_db_query(conn, sql, params=None):
        calls["last_sql"] = sql
        calls["last_params"] = tuple(params or ())
        # Набор строк будем задавать в самом тесте через атрибут
        return getattr(_fake_db_query, "_rows", [])

    monkeypatch.setattr(app_module, "db_query", _fake_db_query, raising=True)

    # Прокидываем «внутренние» штуки наружу для ассертов
    app_module._test_calls = calls
    app_module._fake_db_query = _fake_db_query  # доступ, чтобы подменять _rows из тестов

    yield app_module

@pytest.fixture
def client_with_key(app_with_key_and_mocks):
    app_with_key_and_mocks.app.config["TESTING"] = True
    return app_with_key_and_mocks.app.test_client()

# ------------------- Позитивные кейсы -------------------

def test_catalog_search_ok(client_with_key, app_with_key_and_mocks):
    # Подготовим фейковые строки, которые вернет db_query
    app_with_key_and_mocks._fake_db_query._rows = [
        {
            "code": "R1",
            "name": "Rioja Tinto",
            "producer": "Bodega",
            "region": "Rioja",
            "color": "red",
            "price_list_rub": 1000,
            "price_final_rub": 900,
            "stock_total": 10,
            "stock_free": 8,
        },
        {
            "code": "R2",
            "name": "Rioja Blanco",
            "producer": "Bodega",
            "region": "Rioja",
            "color": "white",
            "price_list_rub": 1100,
            "price_final_rub": 990,
            "stock_total": 5,
            "stock_free": 5,
        },
    ]

    r = client_with_key.get("/catalog/search?q=Rioja&in_stock=1&limit=2")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert data["items"][0]["code"] == "R1"

    # Проверим, какие параметры ушли в SQL (like x3 + limit)
    params = app_with_key_and_mocks._test_calls["last_params"]
    assert params == ("%Rioja%", "%Rioja%", "%Rioja%", 2)

def test_sku_card_ok(client_with_key, app_with_key_and_mocks):
    app_with_key_and_mocks._fake_db_query._rows = [
        {
            "code": "ABC",
            "name": "Rioja Tinto",
            "producer": "Bodega",
            "region": "Rioja",
            "color": "red",
            "style": "dry",
            "price_list_rub": 1000,
            "price_final_rub": 900,
            "stock_total": 10,
            "stock_free": 8,
        }
    ]
    r = client_with_key.get("/sku/ABC", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["code"] == "ABC"
    # Параметры для where p.code = %s
    assert app_with_key_and_mocks._test_calls["last_params"] == ("ABC",)

def test_price_history_ok(client_with_key, app_with_key_and_mocks):
    app_with_key_and_mocks._fake_db_query._rows = [
        {"code": "ABC", "price_rub": 950, "effective_from": "2025-01-01T00:00:00", "effective_to": None},
        {"code": "ABC", "price_rub": 900, "effective_from": "2024-12-01T00:00:00", "effective_to": "2024-12-31T23:59:59"},
    ]
    r = client_with_key.get(
        "/sku/ABC/price-history?from=2024-12-01&to=2025-01-31&limit=2&offset=0",
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert data["items"][0]["price_rub"] == 950

    # Порядок параметров: code, from, to, limit, offset
    assert _norm_params(app_with_key_and_mocks._test_calls["last_params"]) == (
        "ABC", "2024-12-01", "2025-01-31", 2, 0
    )

def test_inventory_history_ok(client_with_key, app_with_key_and_mocks):
    app_with_key_and_mocks._fake_db_query._rows = [
        {"code": "ABC", "stock_total": 10, "reserved": 2, "stock_free": 8, "as_of": "2025-01-10T10:00:00"},
        {"code": "ABC", "stock_total": 12, "reserved": 1, "stock_free": 11, "as_of": "2025-01-05T10:00:00"},
    ]
    r = client_with_key.get(
        "/sku/ABC/inventory-history?from=2025-01-01&to=2025-01-31&limit=2",
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert data["items"][1]["stock_free"] == 11

    # Порядок параметров: code, from, to, limit, offset
    # offset по умолчанию 0
    assert _norm_params(app_with_key_and_mocks._test_calls["last_params"]) == (
        "ABC", "2025-01-01", "2025-01-31", 2, 0
    )


    def test_products_search_country_filter(client):
        """
        Поиск по country должен возвращать только товары из указанной страны
        (или подстроку в названии страны).
        """
        resp = client.get(
            "/api/v1/products/search",
            query_string={"country": "Южная Африка", "limit": "50"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        items = data["items"]

        # Должен быть хотя бы один результат, иначе тест не имеет смысла
        assert len(items) > 0

        for item in items:
            # В ответе должен быть country, и он должен содержать искомую строку
            assert "country" in item
            assert isinstance(item["country"], str)
            assert "Южная Африка" in item["country"]

    def test_products_search_price_range_filter(client):
        """
        min_price / max_price должны ограничивать диапазон цен в выдаче.
        Проверяем, что все price_final_rub попадают в заданный интервал.
        """
        min_price = 2000
        max_price = 5000

        resp = client.get(
            "/api/v1/products/search",
            query_string={
                "min_price": str(min_price),
                "max_price": str(max_price),
                "limit": "50",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        items = data["items"]

        assert len(items) > 0

        for item in items:
            # price_final_rub может приходить строкой — приводим к float
            price_str = item.get("price_final_rub")
            assert price_str is not None
            price = float(price_str)
            assert min_price <= price <= max_price

    def test_products_search_in_stock_true_returns_only_items_with_stock(
            client):
        """
        in_stock=true должен фильтровать товары без остатка:
        ожидаем, что stock_free > 0 для всех элементов.
        """
        resp = client.get(
            "/api/v1/products/search",
            query_string={"in_stock": "true", "limit": "50"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        items = data["items"]

        # Может оказаться пустым, если данных нет, но если что-то есть —
        # у всех должен быть положительный stock_free.
        for item in items:
            stock_free = item.get("stock_free")
            # При нашем SQL (WHERE i.stock_free > 0) NULL быть не должно, но проверим на всякий.
            assert stock_free is not None
            assert stock_free > 0
