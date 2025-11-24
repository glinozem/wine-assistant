from __future__ import annotations

import io

import openpyxl


def test_export_search_json_smoke(client):
    """JSON-экспорт поиска: базовая проверка, что всё отвечает и формат корректный."""
    resp = client.get("/export/search?format=json&limit=5")

    assert resp.status_code == 200
    # Flask test client: get_json() вернёт уже распарсенный JSON
    data = resp.get_json()
    assert isinstance(data, list)


def test_export_search_xlsx_headers_and_attachment(client):
    """
    Excel-экспорт поиска:
    - корректный Content-Type
    - заголовок attachment
    - в файле есть ожидаемые заголовки колонок
    """
    resp = client.get("/export/search?format=xlsx&limit=5")

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
        "Код",
        "Название",
        "Цена прайс",
        "Цена финальная",
        "Цвет",
        "Регион",
        "Производитель",
    ]


def test_export_search_pdf_basic(client):
    """
    PDF-экспорт поиска:
    - корректный Content-Type
    - attachment
    - начало файла соответствует PDF-формату (%PDF)
    """
    resp = client.get("/export/search?format=pdf&limit=5")

    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type", "")
    assert content_type.startswith("application/pdf")

    content_disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in content_disposition

    # Очень простая проверка, что это действительно PDF
    assert resp.data.startswith(b"%PDF")


def test_export_search_unsupported_format_returns_400(client):
    """Неподдерживаемый формат должен вернуть 400 и тело с ошибкой."""
    resp = client.get("/export/search?format=yaml")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "unsupported_format"
    assert "yaml" not in data.get("supported", [])
