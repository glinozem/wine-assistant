"""
Unit tests for scripts/load_csv.py
Testing data loading and processing functions.
"""
import pytest
import sys
import os

# Добавляем путь к scripts в sys.path, чтобы импортировать load_csv
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))

from scripts.load_csv import _norm, _to_float, _to_int, _norm_key, _get_discount_from_cell


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
        ws['S5'] = '10%'  # Устанавливаем скидку

        excel_file = tmp_path / "test_discount.xlsx"
        wb.save(excel_file)

        # Act - вызываем функцию
        result = _get_discount_from_cell(str(excel_file), 0, 'S5')

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
        ws['S5'] = 0.15  # Число (не строка!)

        excel_file = tmp_path / "test_discount_decimal.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, 'S5')

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
        ws['S5'] = 10  # Число больше 1 -> должно разделиться на 100

        excel_file = tmp_path / "test_discount_large.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, 'S5')

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
        result = _get_discount_from_cell(str(excel_file), 0, 'S5')

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
        ws['S5'] = 'invalid'  # Некорректное значение

        excel_file = tmp_path / "test_discount_invalid.xlsx"
        wb.save(excel_file)

        # Act
        result = _get_discount_from_cell(str(excel_file), 0, 'S5')

        # Assert
        assert result is None
