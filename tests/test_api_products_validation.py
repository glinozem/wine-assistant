# tests/test_api_products_validation.py
import importlib
import os
import types

import pytest


@pytest.fixture
def app_with_api_key(monkeypatch):
    # Гарантируем, что API_KEY включён
    monkeypatch.setenv("API_KEY", "test-key")
    # Перезагружаем модуль app, чтобы подтянул переменные окружения
    from api import app as app_module
    importlib.reload(app_module)
    yield app_module.app

@pytest.fixture
def client_with_key(app_with_api_key):
    app_with_api_key.config["TESTING"] = True
    return app_with_api_key.test_client()

def test_price_history_invalid_range_returns_400(client_with_key):
    r = client_with_key.get(
        "/sku/ABC/price-history?from=2025-01-10&to=2025-01-01",
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data["error"] == "validation_error"

def test_price_history_invalid_limit_returns_400(client_with_key):
    r = client_with_key.get(
        "/sku/ABC/price-history?limit=1001",
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "validation_error"

def test_inventory_history_negative_offset_returns_400(client_with_key):
    r = client_with_key.get(
        "/sku/ABC/inventory-history?offset=-1",
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "validation_error"

def test_protected_without_key_returns_403(app_with_api_key):
    c = app_with_api_key.test_client()
    r = c.get("/sku/ABC")
    assert r.status_code == 403
