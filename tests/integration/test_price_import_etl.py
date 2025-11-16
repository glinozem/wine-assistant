import os
import sys
from pathlib import Path

import pytest

from scripts.load_csv import main as load_csv_main

# Такой же флаг, как и в tests/unit/test_load_utils.py
RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL and RUN_DB_TESTS=1",
)
def test_price_import_smoke(tmp_path):
    """
    Простейший end-to-end тест:
    - готовим маленький CSV с кодом и ценой
    - вызываем настоящий main() из load_csv.py
    - проверяем, что он отрабатывает без исключений
      (остальное будет в следующих, более детальных тестах)
    """

    # 1. Подготавливаем временный CSV-файл
    csv_path: Path = tmp_path / "test_price.csv"
    csv_path.write_text("Код;Цена\nTEST001;123.45\n", encoding="utf-8")

    # 2. Подменяем sys.argv так же, как в unit-тестах
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]

    # 3. Запускаем ETL.
    # Если что-то не так с БД/миграциями/логикой — тест упадёт по исключению.
    load_csv_main()
