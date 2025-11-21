import importlib
import os
import time

import pytest

# Важно: до импорта приложения задаём лимиты, чтобы лимитер инициализировался как нужно
os.environ["RATE_LIMIT_ENABLED"] = "1"
os.environ["RATE_LIMIT_PUBLIC"] = "3/minute"
os.environ["RATE_LIMIT_STORAGE_URL"] = "memory://"

# Импорт приложения
from api import app as app_module  # noqa: E402

importlib.reload(app_module)       # на случай переинициализации при перезапусках тестов
app = app_module.app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_200_and_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.is_json
    assert r.json == {"ok": True}
    # Трассировочный header
    assert "X-Request-ID" in r.headers


def test_rate_limit_headers_and_429(client):
    # Три успешных запроса (лимит 3/min)…
    r1 = client.get("/health")
    r2 = client.get("/health")
    r3 = client.get("/health")
    # Заголовки лимитера присутствуют
    for r in (r1, r2, r3):
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers
        assert "X-RateLimit-Reset" in r.headers

    # …четвёртый — уже 429
    r4 = client.get("/health")
    assert r4.status_code == 429
    assert r4.is_json
    assert r4.json.get("error") == "rate_limited"
