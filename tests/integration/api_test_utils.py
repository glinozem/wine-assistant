# tests/integration/api_test_utils.py
import os
from typing import Any

import pytest
import requests

# Базовый URL и ключ для внешних HTTP-запросов (через requests)
API_URL = os.getenv("API_URL", "http://localhost:18000")
API_KEY = os.getenv("API_KEY")

# Общий эндпоинт поиска товаров
SEARCH_ENDPOINT = "/api/v1/products/search"


def _call_protected_api_json(
    path: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """
    Вспомогательный helper для GET-запроса к защищённому API.

    - Добавляет base_url (из API_BASE_URL / API_URL, если не передан явно)
    - Подставляет X-API-Key
    - Делает pytest.skip, если API недоступен
    - Проверяет статус 200 и парсит JSON
    """
    if api_key is None:
        api_key = API_KEY or os.getenv("API_KEY")
    if not api_key:
        pytest.skip("API_KEY is not set in environment, cannot call protected API")

    if base_url is None:
        base_url = os.getenv("API_BASE_URL", API_URL)

    # Нормализуем склейку, чтобы не получить '//' в URL
    if path.startswith("/"):
        url = f"{base_url}{path}"
    else:
        url = f"{base_url.rstrip('/')}/{path}"

    try:
        resp = requests.get(
            url,
            headers={"X-API-Key": api_key},
            timeout=10,
        )
    except requests.RequestException as exc:
        pytest.skip(f"API not reachable at {url}: {exc}")

    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"

    try:
        return resp.json()
    except ValueError as exc:
        pytest.fail(f"Cannot decode JSON from {url}: {exc}")


def _search_products(client, **query_params) -> list[dict[str, Any]]:
    """
    Helper для вызова /api/v1/products/search через Flask test client.

    - Подставляет limit=50 по умолчанию.
    - Делает GET, проверяет 200.
    - Возвращает список items.
    """
    params: dict[str, str] = {"limit": "50"}
    for key, value in query_params.items():
        if value is None:
            continue
        params[key] = str(value)

    resp = client.get(SEARCH_ENDPOINT, query_string=params)
    assert resp.status_code == 200
    data = resp.get_json()
    return data["items"]
