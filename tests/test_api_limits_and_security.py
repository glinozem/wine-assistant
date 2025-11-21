# tests/test_api_limits_and_security.py
import importlib
import os
import sys


def _reload_app_with_env(env_overrides: dict):
    """
    Жёстко переимпортируем api.app с новыми переменными окружения.
    ВАЖНО: используем import_module вместо reload, т.к. мы чистим кэш модулей.
    """
    # Применяем переменные окружения
    for k, v in env_overrides.items():
        os.environ[k] = v

    # Чистим кэш, чтобы декораторы и конфиги перечитались
    sys.modules.pop("api.app", None)
    # Пакет "api" оставляем — он не критичен, но если хочешь — можно тоже чистить:
    # sys.modules.pop("api", None)

    app_module = importlib.import_module("api.app")
    return app_module.app


def test_public_rate_limit_headers_and_429():
    """
    На /health действуют публичные лимиты. Проверяем:
    - первые 3 запроса 200 + есть X-RateLimit-* заголовки
    - 4-й запрос -> 429 с JSON {"error":"rate_limited", ...}
    """
    app = _reload_app_with_env(
        {
            "RATE_LIMIT_ENABLED": "1",
            "RATE_LIMIT_STORAGE_URL": "memory://",
            "RATE_LIMIT_PUBLIC": "3/minute",
            "RATELIMIT_HEADERS_ENABLED": "true",
        }
    )
    client = app.test_client()

    # Фиксируем IP, чтобы лимитер считал это одним клиентом.
    common_headers = {"X-Forwarded-For": "9.9.9.1"}

    # 1..3 — OK + заголовки присутствуют
    hdr_snapshots = []
    for _ in range(3):
        r = client.get("/health", headers=common_headers)
        assert r.status_code == 200
        hdr_snapshots.append(
            (
                r.headers.get("X-RateLimit-Limit"),
                r.headers.get("X-RateLimit-Remaining"),
                r.headers.get("X-RateLimit-Reset"),
            )
        )
        assert hdr_snapshots[-1][0] is not None
        assert hdr_snapshots[-1][1] is not None
        assert hdr_snapshots[-1][2] is not None

    # 4-й — должен сработать лимит
    r = client.get("/health", headers=common_headers)
    assert r.status_code == 429
    data = r.get_json()
    assert data and data.get("error") == "rate_limited"


def test_protected_endpoints_require_api_key_missing():
    """
    Без X-API-Key доступ к защищённым SKU-роутам запрещён.
    """
    app = _reload_app_with_env(
        {
            "RATE_LIMIT_ENABLED": "0",  # чтобы лимитер не мешал
            "API_KEY": "test-key",
        }
    )
    client = app.test_client()

    assert client.get("/sku/ABC").status_code == 403
    assert client.get("/sku/ABC/price-history").status_code == 403
    assert client.get("/sku/ABC/inventory-history").status_code == 403


def test_protected_endpoints_require_api_key_invalid():
    """
    Неверный ключ — тоже 403.
    """
    app = _reload_app_with_env(
        {
            "RATE_LIMIT_ENABLED": "0",
            "API_KEY": "test-key",
        }
    )
    client = app.test_client()

    headers = {"X-API-Key": "bad-key"}
    assert client.get("/sku/ABC", headers=headers).status_code == 403
    assert client.get("/sku/ABC/price-history", headers=headers).status_code == 403
    assert client.get("/sku/ABC/inventory-history", headers=headers).status_code == 403
