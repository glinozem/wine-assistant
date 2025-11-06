import os
import sys
import uuid
from datetime import date

import pandas as pd
import psycopg2
import pytest
from openpyxl import Workbook

# Добавляем путь к scripts в sys.path, чтобы импортировать load_csv
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.load_utils import (
    _canonicalize_headers,
    _get_discount_from_cell,
    _norm,
    _norm_key,
    _to_float,
    _to_int,
    get_conn,
    read_any,
    upsert_records,
)

# =============================================================================
# Tests for _norm() function
# =============================================================================


@pytest.mark.unit
def test_norm_removes_leading_and_trailing_spaces():
    """
    Test: _norm() should remove spaces at the beginning and end.
    """
    # Arrange
    input_string = "  hello world  "

    # Act
    result = _norm(input_string)

    # Assert
    assert result == "hello world"


@pytest.mark.unit
def test_norm_replaces_newlines_with_spaces():
    """
    Test: _norm() should replace \\n with space.
    """
    # Arrange
    input_string = "hello\nworld"

    # Act
    result = _norm(input_string)

    # Assert
    assert result == "hello world"


@pytest.mark.unit
def test_norm_handles_none():
    """
    Test: _norm(None) should return empty string.
    """
    # Arrange
    input_value = None

    # Act
    result = _norm(input_value)

    # Assert
    assert result == ""


@pytest.mark.unit
def test_norm_collapses_multiple_spaces():
    """
    Test: _norm() should collapse multiple spaces into one.
    """
    # Arrange
    input_string = "hello    world"

    # Act
    result = _norm(input_string)

    # Assert
    assert result == "hello world"


# =============================================================================
# Tests for _to_float() function
# =============================================================================


@pytest.mark.unit
def test_to_float_converts_string_to_float():
    """
    Test: _to_float() should convert string "1000" to 1000.0
    """
    # Arrange
    input_string = "1000"

    # Act
    result = _to_float(input_string)

    # Assert
    assert result == 1000.0


@pytest.mark.unit
def test_to_float_handles_spaces_in_numbers():
    """
    Test: _to_float() should handle "1 000" (with spaces).
    """
    # Arrange
    input_string = "1 000"

    # Act
    result = _to_float(input_string)

    # Assert
    assert result == 1000.0


@pytest.mark.unit
def test_to_float_handles_comma_as_decimal_separator():
    """
    Test: _to_float() should convert "1000,50" to 1000.5
    """
    # Arrange
    input_string = "1000,50"

    # Act
    result = _to_float(input_string)

    # Assert
    assert result == 1000.5


@pytest.mark.unit
def test_to_float_handles_none():
    """
    Test: _to_float(None) should return None.
    """
    # Arrange
    input_value = None

    # Act
    result = _to_float(input_value)

    # Assert
    assert result is None


@pytest.mark.unit
def test_to_float_handles_negative_numbers():
    """
    Test: _to_float() should handle negative numbers.
    """
    # Arrange
    input_string = "-42.5"

    # Act
    result = _to_float(input_string)

    # Assert
    assert result == -42.5


# =============================================================================
# Tests for _to_int() function
# =============================================================================


@pytest.mark.unit
def test_to_int_converts_string_to_int():
    """
    Test: _to_int() should convert "42" to 42.
    """
    # Arrange
    input_string = "42"

    # Act
    result = _to_int(input_string)

    # Assert
    assert result == 42


@pytest.mark.unit
def test_to_int_rounds_float_to_int():
    """
    Test: _to_int() should round "42.7" to 43.
    """
    # Arrange
    input_string = "42.7"

    # Act
    result = _to_int(input_string)

    # Assert
    assert result == 43


@pytest.mark.unit
def test_to_int_handles_none():
    """
    Test: _to_int(None) should return None.
    """
    # Arrange
    input_value = None

    # Act
    result = _to_int(input_value)

    # Assert
    assert result is None


# =============================================================================
# Tests for _norm_key() function
# =============================================================================


@pytest.mark.unit
def test_norm_key_converts_to_lowercase():
    """
    Test: _norm_key() should convert to lowercase.
    """
    # Arrange
    input_string = "ЦЕНА"

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "цена"


@pytest.mark.unit
def test_norm_key_replaces_spaces_with_underscores():
    """
    Test: _norm_key() should replace spaces with underscores.
    """
    # Arrange
    input_string = "Цена прайс"

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "цена_прайс"


@pytest.mark.unit
def test_norm_key_replaces_yo_with_ye():
    """
    Test: _norm_key() should replace 'ё' with 'е'.
    """
    # Arrange
    input_string = "объём"

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "объем"


@pytest.mark.unit
def test_norm_key_handles_percent_sign():
    """
    Test: _norm_key() removes special characters including percent sign.
    """
    # Arrange
    input_string = "Алк, %"

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "алк"


@pytest.mark.unit
def test_norm_key_removes_special_characters():
    """
    Test: _norm_key() should remove special characters (commas, dots, etc).
    """
    # Arrange
    input_string = "Цена, руб."

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "цена_руб"


@pytest.mark.unit
def test_norm_key_collapses_multiple_underscores():
    """
    Test: _norm_key() should collapse multiple underscores into one.
    """
    # Arrange
    input_string = "Цена___прайс"

    # Act
    result = _norm_key(input_string)

    # Assert
    assert result == "цена_прайс"


# =============================================================================
# Tests for _get_discount_from_cell() function
# =============================================================================


class TestGetDiscountFromCell:
    """
    Тесты для извлечения скидки из ячейки Excel.

    Функция _get_discount_from_cell() читает значение из указанной ячейки
    Excel файла и парсит скидку в формате доли (0.0 - 1.0).

    Поддерживаемые форматы:
    - "10%" -> 0.10
    - "0.15" -> 0.15
    - 10 (число > 1) -> 0.10
    - None -> None (пустая ячейка)
    - "invalid" -> None (некорректный формат)
    """

    @pytest.mark.unit
    def test_discount_percentage_format(self, tmp_path):
        """
        Test: Скидка в формате "10%" должна преобразоваться в 0.10

        Arrange: Создаём тестовый Excel файл с "10%" в ячейке S5
        Act: Вызываем _get_discount_from_cell()
        Assert: Проверяем, что вернулось 0.10
        """
        # Arrange - создаём тестовый Excel файл
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws["S5"] = "10%"  # Устанавливаем скидку

        excel_file = tmp_path / "test_discount.xlsx"
        wb.save(excel_file)

        # Act - вызываем функцию
        result = _get_discount_from_cell(str(excel_file), 0, "S5")

        # Assert - проверяем результат
        assert result == 0.10

    @pytest.mark.unit
    def test_discount_decimal_format(self, tmp_path):
        """
        Test: Скидка в формате 0.15 (десятичная дробь) должна остаться 0.15

        Arrange: Создаём Excel с числом 0.15 в S5
        Act: Вызываем _get_discount_from_cell()
        Assert: Проверяем, что вернулось 0.15
        """
        # Arrange
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws["S5"] = 0.15  # Число (не строка!)

        excel_file = tmp_path / "test_discount_decimal.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, "S5")

        # Assert
        assert result == 0.15

    @pytest.mark.unit
    def test_discount_large_number_format(self, tmp_path):
        """
        Test: Скидка 10 (число > 1) должна преобразоваться в 0.10

        Arrange: Создаём Excel с числом 10 в S5
        Act: Вызываем _get_discount_from_cell()
        Assert: Проверяем, что вернулось 0.10 (10% = 0.10)
        """
        # Arrange
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws["S5"] = 10  # Число больше 1 -> должно разделиться на 100

        excel_file = tmp_path / "test_discount_large.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, "S5")

        # Assert
        assert result == 0.10

    @pytest.mark.unit
    def test_discount_empty_cell(self, tmp_path):
        """
        Test: Пустая ячейка S5 должна возвращать None

        Arrange: Создаём Excel с пустой ячейкой S5
        Act: Вызываем _get_discount_from_cell()
        Assert: Проверяем, что вернулось None
        """
        # Arrange
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        # S5 остаётся пустой (не устанавливаем значение)

        excel_file = tmp_path / "test_discount_empty.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, "S5")

        # Assert
        assert result is None

    @pytest.mark.unit
    def test_discount_invalid_format(self, tmp_path):
        """
        Test: Некорректный формат ("invalid") должен возвращать None

        Arrange: Создаём Excel с текстом "invalid" в S5
        Act: Вызываем _get_discount_from_cell()
        Assert: Проверяем, что вернулось None
        """
        # Arrange
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws["S5"] = "invalid"  # Некорректное значение

        excel_file = tmp_path / "test_discount_invalid.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, "S5")

        # Assert
        assert result is None


# =============================================================================
# NEW TESTS: High-level functions
# =============================================================================


class TestCanonicalizeHeaders:
    """
    Тесты для функции _canonicalize_headers()

    Функция маппит заголовки колонок на канонические имена согласно COLMAP.
    """

    @pytest.mark.unit
    def test_canonicalize_headers_maps_correctly(self):
        """
        Test: _canonicalize_headers должна правильно маппить известные колонки

        Arrange: Список колонок с русскими и английскими названиями
        Act: Вызываем _canonicalize_headers()
        Assert: Проверяем что колонки замапились правильно
        """
        # Arrange
        cols = ["Код", "Производитель", "Название", "Цена прайс", "Цена со скидкой"]

        # Act
        result = _canonicalize_headers(cols)

        # Assert
        assert result["Код"] == "code"
        assert result["Производитель"] == "producer"
        assert result["Название"] == "title_ru"
        assert result["Цена прайс"] == "price_rub"
        assert result["Цена со скидкой"] == "price_discount"

    @pytest.mark.unit
    def test_canonicalize_headers_handles_unnamed(self):
        """
        Test: _canonicalize_headers должна игнорировать unnamed колонки

        Arrange: Список колонок с unnamed и пустыми названиями
        Act: Вызываем _canonicalize_headers()
        Assert: Проверяем что unnamed колонки замапились на None
        """
        # Arrange
        cols = ["Unnamed: 0", "Код", "", "Цена", "unnamed_5"]

        # Act
        result = _canonicalize_headers(cols)

        # Assert
        assert result["Unnamed: 0"] is None
        assert result["Код"] == "code"
        assert result[""] is None
        assert result["Цена"] == "price_rub"
        assert result["unnamed_5"] is None

    @pytest.mark.unit
    def test_canonicalize_headers_handles_discount_with_percent(self):
        """
        Test: _canonicalize_headers должна распознавать "Цена со скидкой 10%"

        Arrange: Колонка с процентом в названии
        Act: Вызываем _canonicalize_headers()
        Assert: Проверяем что замапилась на price_discount
        """
        # Arrange
        cols = ["Код", "Цена со скидкой 10%"]

        # Act
        result = _canonicalize_headers(cols)

        # Assert
        assert result["Код"] == "code"
        assert result["Цена со скидкой 10%"] == "price_discount"


class TestReadAny:
    """
    Тесты для функции read_any()

    Функция универсального чтения CSV/Excel файлов с авто-определением параметров.
    """

    @pytest.mark.unit
    def test_read_any_detects_csv_encoding(self, tmp_path):
        """
        Test: read_any должна автоматически определять кодировку CSV

        Arrange: Создаём CSV файл в cp1251
        Act: Вызываем read_any()
        Assert: Проверяем что данные прочитались корректно
        """
        # Arrange - создаём CSV с русскими символами в cp1251
        csv_file = tmp_path / "test_encoding.csv"
        csv_content = "Код,Название,Цена\n123,Тестовое вино,1000\n456,Другое вино,2000"
        csv_file.write_bytes(csv_content.encode("cp1251"))

        # Act
        df = read_any(str(csv_file))

        # Assert
        assert "code" in df.columns
        assert len(df) == 2
        assert df.iloc[0]["code"] == "123"

    @pytest.mark.unit
    def test_read_any_handles_excel_basic(self, tmp_path):
        """
        Test: read_any должна читать базовый Excel файл

        Arrange: Создаём простой Excel с заголовками
        Act: Вызываем read_any()
        Assert: Проверяем что колонки замапились правильно
        """
        # Arrange
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "Код"
        ws["B1"] = "Название"
        ws["C1"] = "Цена"
        ws["A2"] = "123"
        ws["B2"] = "Вино"
        ws["C2"] = "1000"

        excel_file = tmp_path / "test_basic.xlsx"
        wb.save(excel_file)

        # Act
        df = read_any(str(excel_file))

        # Assert
        assert "code" in df.columns
        assert "title_ru" in df.columns
        assert "price_rub" in df.columns
        assert len(df) == 1
        assert df.iloc[0]["code"] == "123"

    @pytest.mark.unit
    def test_read_any_finds_code_column(self, tmp_path):
        """
        Test: read_any должна находить колонку с кодом по разным вариантам

        Arrange: Создаём Excel с колонкой "Артикул" вместо "Код"
        Act: Вызываем read_any()
        Assert: Проверяем что колонка переименовалась в "code"
        """
        # Arrange
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "Артикул"
        ws["B1"] = "Название"
        ws["A2"] = "WINE123"
        ws["B2"] = "Красное вино"

        excel_file = tmp_path / "test_article.xlsx"
        wb.save(excel_file)

        # Act
        df = read_any(str(excel_file))

        # Assert
        assert "code" in df.columns
        assert df.iloc[0]["code"] == "WINE123"


def test_get_conn_returns_valid_connection(monkeypatch):
    # Установка переменных окружения для подключения
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "15432")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPASSWORD", "dev_local_pw")
    monkeypatch.setenv("PGDATABASE", "wine_db")

    conn = get_conn()
    assert conn is not None
    assert isinstance(conn, psycopg2.extensions.connection)

    # Проверка, что подключение работает
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
        result = cur.fetchone()
        assert result[0] == 1

    conn.close()


def test_upsert_records_insert_and_update(monkeypatch):
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "15432")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPASSWORD", "dev_local_pw")
    monkeypatch.setenv("PGDATABASE", "wine_db")

    conn = get_conn()
    test_uuid = uuid.uuid4()

    # DataFrame вместо списка словарей
    df = pd.DataFrame(
        [
            {
                "code": "TEST001",
                "envelope_id": test_uuid,
                "price_rub": 100.0,
                "price_discount": 90.0,
                "price_final_rub": 90.0,
            }
        ]
    )

    # Тестовая дата
    today = date.today()

    # First insert
    inserted = upsert_records(df, today)
    assert inserted == 1

    # Try update same record
    df.loc[0, "price_discount"] = 85.0
    updated = upsert_records(df, today)
    assert updated == 1

    conn.close()
