from __future__ import annotations

import io

import openpyxl


def test_export_search_json_smoke(client):
    """
    JSON-экспорт поиска: базовая проверка, что всё отвечает и формат корректный.
    Ожидаем формат: {"Count": <int>, "value": [ {...}, ... ]}.
    """
    resp = client.get("/export/search?format=json&limit=5")

    assert resp.status_code == 200

    data = resp.get_json()
    # Новый формат — не список, а словарь с Count и value
    assert isinstance(data, dict)

    assert "Count" in data
    assert "value" in data

    assert isinstance(data["Count"], int)
    assert isinstance(data["value"], list)
    assert data["Count"] == len(data["value"])

    # Минимальная проверка структуры элемента
    if data["value"]:
        item = data["value"][0]
        assert isinstance(item, dict)
        assert "code" in item
        assert "title_ru" in item
        assert "price_final_rub" in item


def test_export_search_xlsx_headers_and_attachment(client):
    """
    Excel-экспорт поиска:
    - корректный Content-Type
    - заголовок attachment
    - в файле есть ожидаемые заголовки колонок (полный набор DEFAULT_SEARCH_COLUMNS)
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

    # Должен совпадать с DEFAULT_SEARCH_COLUMNS в api.export.ExportService
    assert header_row == [
        "Код",
        "Название",
        "Цена прайс",
        "Цена финальная",
        "Цвет",
        "Регион",
        "Производитель",
        "Сортовой состав",
        "Год урожая",
        "Рейтинг Vivino",
        "Экспертный рейтинг",
        "Поставщик",
        "Сайт производителя",
        "Фото (URL)",
    ]
