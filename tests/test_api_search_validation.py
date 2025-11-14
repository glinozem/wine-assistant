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
