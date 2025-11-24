# tests/integration/test_api_export_sku_and_price_history.py
from __future__ import annotations

import importlib
import io

import openpyxl
import pytest

from api import app as app_module  # noqa: E402
from tests.integration.api_test_utils import _search_products

importlib.reload(app_module)
app = app_module.app


@pytest.fixture
def client():
    """
    Flask test client для защищённых экспортных эндпоинтов.

    Здесь мы временно отключаем проверку API key (app_module.API_KEY),
    чтобы тесты не зависели от переменных окружения. Логику require_api_key
    проверяют отдельные тесты в test_api_limits_and_security.py.
    """
    original_api_key = getattr(app_module, "API_KEY", None)
    app_module.API_KEY = None

    app.config["TESTING"] = True
    try:
        with app.test_client() as c:
            yield c
    finally:
        app_module.API_KEY = original_api_key


def _get_any_sku_code(client) -> str:
    """
    Берём любой существующий код товара через /api/v1/products/search.

    Если каталог пустой (что маловероятно в нормальном окружении), тест
    помечается как skipped.
    """
    items = _search_products(client, limit=1)

    if not items:
        pytest.skip("No products in catalog — cannot test export endpoints")

    code = items[0].get("code")
    assert code, "Search item has no 'code'"
    return str(code)


# -------------------------------------------------------------------------
# /export/sku/<code>
# -------------------------------------------------------------------------


def test_export_sku_json_smoke(client):
    """JSON-экспорт карточки товара: базовая проверка, что всё отвечает."""
    code = _get_any_sku_code(client)

    resp = client.get(f"/export/sku/{code}?format=json")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert data.get("code") == code

    # Пара базовых полей, которые почти всегда есть в SKU
    assert "title_ru" in data
    assert "price_final_rub" in data


def test_export_sku_pdf_basic(client):
    """
    PDF-экспорт карточки товара:
    - корректный Content-Type
    - attachment в Content-Disposition
    - начало файла соответствует PDF (%PDF)
    """
    code = _get_any_sku_code(client)

    resp = client.get(f"/export/sku/{code}?format=pdf")

    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type", "")
    assert content_type.startswith("application/pdf")

    content_disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in content_disposition

    # Очень простая проверка, что это действительно PDF
    assert resp.data.startswith(b"%PDF")


def test_export_sku_not_found_returns_404(client):
    """Запрос на несуществующий код должен вернуть 404 и error=not_found."""
    resp = client.get("/export/sku/THIS_CODE_DOES_NOT_EXIST?format=json")

    assert resp.status_code == 404
    data = resp.get_json()
    assert data.get("error") == "not_found"


# -------------------------------------------------------------------------
# /export/price-history/<code>
# -------------------------------------------------------------------------


def test_export_price_history_json_smoke(client):
    """
    JSON-экспорт истории цен:
    - 200 OK
    - корректная структура (dict с code и items)
    """
    code = _get_any_sku_code(client)

    resp = client.get(f"/export/price-history/{code}?format=json")

    if resp.status_code == 404:
        pytest.skip(f"No price history for code={code}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, dict)
    assert payload.get("code") == code
    assert isinstance(payload.get("items"), list)


def test_export_price_history_xlsx_headers_and_attachment(client):
    """
    Excel-экспорт истории цен:
    - корректный Content-Type
    - attachment в Content-Disposition
    - в файле есть ожидаемые заголовки колонок
    """
    code = _get_any_sku_code(client)

    resp = client.get(f"/export/price-history/{code}?format=xlsx")

    if resp.status_code == 404:
        pytest.skip(f"No price history for code={code}")

    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type", "")
    assert content_type.startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    content_disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in content_disposition

    # Проверяем, что это валидный XLSX с нужными заголовками
    wb = openpyxl.load_workbook(io.BytesIO(resp.data))
    ws = wb.active

    header_row = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    assert header_row == [
        "Дата начала",
        "Дата окончания",
        "Цена прайс",
        "Цена финальная",
    ]


def test_export_price_history_unsupported_format_returns_400(client):
    """Неподдерживаемый формат должен вернуть 400 и тело с ошибкой."""
    code = _get_any_sku_code(client)

    resp = client.get(f"/export/price-history/{code}?format=yaml")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("error") == "unsupported_format"
