import hashlib
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

from scripts.load_csv import main as load_csv_main
from scripts.load_utils import get_conn

# Такой же флаг, как и в tests/unit/test_load_utils.py
RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"

API_URL = os.getenv("API_URL", "http://localhost:18000")
API_KEY = os.getenv("API_KEY")

def _compute_sha256(path: Path) -> str:
    """Локальный helper для SHA256, чтобы найти наш файл в ingest_envelope."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


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


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL and RUN_DB_TESTS=1",
)
def test_price_import_persists_data(tmp_path):
    """
    Более детальный end-to-end тест:
    - генерируем уникальный SKU и CSV-файл
    - измеряем состояние ingest_envelope и product_prices до импорта
    - запускаем реальный ETL (load_csv.main)
    - проверяем, что:
      * в ingest_envelope есть запись с нашим SHA256 и status='success'
      * в product_prices появилась хотя бы одна строка по нашему коду
      * в products есть строка с этим кодом и заполненным ценовым полем
    """

    # Уникальный код, чтобы не пересекаться с реальными SKU
    code = f"INTTEST_{uuid.uuid4().hex[:8]}"
    csv_path: Path = tmp_path / "test_price_persist.csv"
    csv_path.write_text(f"Код;Цена\n{code};123.45\n", encoding="utf-8")

    file_hash = _compute_sha256(csv_path)

    # Состояние БД до импорта
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Сколько конвертов с этим файлом уже есть
            cur.execute(
                "SELECT COUNT(*) FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,),
            )
            envelope_before = cur.fetchone()[0]

            # Сколько исторических цен по нашему коду
            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_before = cur.fetchone()[0]

    # Запуск ETL-пайплайна так же, как в реальной жизни
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    # Состояние БД после импорта
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1) Проверяем, что появился ingest_envelope с нашим файлом
            cur.execute(
                """
                SELECT envelope_id, rows_inserted, status
                  FROM ingest_envelope
                 WHERE file_sha256 = %s
                 ORDER BY upload_timestamp DESC
                 LIMIT 1
                """,
                (file_hash,),
            )
            row = cur.fetchone()
            assert row is not None, "ingest_envelope row was not created"
            envelope_id, rows_inserted, status = row
            assert status == "success"
            assert rows_inserted >= 1

            # 2) Проверяем, что история цен пополнилась
            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after = cur.fetchone()[0]
            assert prices_after >= prices_before + 1

            # 3) Проверяем, что есть товар с этим кодом и ценой
            cur.execute(
                """
                SELECT price_rub, price_list_rub, price_final_rub
                  FROM products
                 WHERE code = %s
                """,
                (code,),
            )
            product_row = cur.fetchone()
            assert product_row is not None, "products row was not created"
            price_rub, price_list_rub, price_final_rub = product_row
            # хотя бы одно из ценовых полей должно быть заполнено
            assert any(
                p is not None for p in (price_rub, price_list_rub, price_final_rub)
            ), "all price fields are NULL for imported product"


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL and RUN_DB_TESTS=1",
)
def test_price_import_idempotent_skip(tmp_path):
    """
    Проверяем идемпотентность ETL по SHA256:
    - первый запуск создаёт ingest_envelope, price_list и записи в product_prices
    - второй запуск с тем же файлом НЕ создаёт новых записей
    """

    code = f"INTTEST_IDEMP_{uuid.uuid4().hex[:8]}"
    csv_path: Path = tmp_path / "test_price_idempotent.csv"
    csv_path.write_text(f"Код;Цена\n{code};123.45\n", encoding="utf-8")

    file_hash = _compute_sha256(csv_path)

    # Состояние БД до импорта
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,),
            )
            envelope_before = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_before = cur.fetchone()[0]

    # Первый запуск ETL
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Должен появиться конверт с нашим файлом
            cur.execute(
                """
                SELECT envelope_id, rows_inserted, status
                  FROM ingest_envelope
                 WHERE file_sha256 = %s
                 ORDER BY upload_timestamp DESC
                 LIMIT 1
                """,
                (file_hash,),
            )
            row = cur.fetchone()
            assert row is not None, "ingest_envelope row was not created on first run"
            envelope_id, rows_inserted, status = row
            assert status == "success"
            assert rows_inserted >= 1

            cur.execute(
                "SELECT COUNT(*) FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,),
            )
            envelope_after_first = cur.fetchone()[0]
            assert envelope_after_first == envelope_before + 1

            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after_first = cur.fetchone()[0]
            assert prices_after_first >= prices_before + 1

            # В price_list должна быть ровно одна запись для этого envelope
            cur.execute(
                "SELECT COUNT(*) FROM price_list WHERE envelope_id = %s",
                (envelope_id,),
            )
            price_list_after_first = cur.fetchone()[0]
            assert price_list_after_first == 1

    # Второй запуск ETL с тем же файлом
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    # Состояние БД после второго запуска
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ingest_envelope WHERE file_sha256 = %s",
                (file_hash,),
            )
            envelope_after_second = cur.fetchone()[0]
            assert (
                envelope_after_second == envelope_after_first
            ), "Second run should not create new ingest_envelope row"

            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after_second = cur.fetchone()[0]
            assert (
                prices_after_second == prices_after_first
            ), "Second run should not add new product_prices rows"

            cur.execute(
                "SELECT COUNT(*) FROM price_list WHERE envelope_id = %s",
                (envelope_id,),
            )
            price_list_after_second = cur.fetchone()[0]
            assert (
                price_list_after_second == price_list_after_first
            ), "Second run should not create additional price_list rows"


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_price_import_db_and_api_price_history(tmp_path):
    """
    Упрощённый сквозной тест для эндпоинта /price-history.

    1. Запускает ETL (load_csv.main) для уникального SKU.
    2. Проверяет, что в product_prices появилась хотя бы одна запись по этому коду.
    3. Дёргает /api/v1/sku/<code>/price-history и проверяет базовую структуру ответа.

    Детальное сравнение значений БД и API выполняется в
    test_price_import_price_history_api_matches_db().
    """

    code = f"INTTEST_API_{uuid.uuid4().hex[:8]}"
    price_str = "123.45"

    # 1. Готовим CSV для ETL
    csv_path: Path = tmp_path / "test_price_api_smoke.csv"
    csv_path.write_text(f"Код;Цена\n{code};{price_str}\n", encoding="utf-8")

    # 2. Запускаем ETL так же, как в остальных интеграционных тестах
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    # 3. Проверяем, что в product_prices есть хотя бы одна запись
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after = cur.fetchone()[0]
            assert prices_after >= 1, "Ожидаем хотя бы одну запись в product_prices"

    # 4. Проверяем HTTP API /api/v1/sku/<code>/price-history
    base_url = os.getenv("API_BASE_URL", API_URL)
    api_key = os.getenv("API_KEY")

    url = f"{base_url}/api/v1/sku/{code}/price-history"
    headers = {"X-API-Key": api_key} if api_key else {}

    try:
        resp = requests.get(
            url,
            headers=headers or None,
            timeout=10,
        )
    except (requests.ConnectionError, requests.Timeout) as exc:
        pytest.skip(f"API not reachable at {url}: {exc}")

    assert resp.status_code == 200, f"Unexpected response: {resp.status_code} {resp.text}"

    payload = resp.json()
    assert payload["code"] == code
    assert payload["total"] >= 1
    assert payload["items"], "API вернул пустой список items"

    # Лёгкая проверка структуры записи
    item = payload["items"][0]
    assert "code" in item
    assert "price_rub" in item
    assert "effective_from" in item


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_price_import_price_history_api_matches_db(tmp_path):
    """
    Сквозной интеграционный тест:

    1. Готовит CSV с одним SKU и ценой.
    2. Запускает ETL через load_csv_main().
    3. Проверяет цену в product_prices через get_conn().
    4. Дёргает /api/v1/sku/<code>/price-history с X-API-Key из окружения
       и сверяет цену из API с ценой в БД.
    """
    # --- подготовка данных ---
    code = f"INTTEST_API_{uuid.uuid4().hex[:8]}"
    price_rub = 123.45

    csv_path: Path = tmp_path / "test_price_api_match.csv"
    csv_path.write_text(
        "Код;Цена\n"
        f"{code};{price_rub}\n",
        encoding="utf-8",
    )

    # --- запуск ETL ---
    sys.argv = [
        "load_csv.py",
        "--csv",
        str(csv_path),
    ]
    # Нам важен не результат функции, а состояние БД после её выполнения
    load_csv_main()

    # --- проверка product_prices в БД ---
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, price_rub
                  FROM product_prices
                 WHERE code = %s
                 ORDER BY effective_from DESC
                 LIMIT 1
                """,
                (code,),
            )
            row = cur.fetchone()

    assert row is not None, "Ожидаем запись в product_prices после ETL"
    db_code, db_price_rub = row
    assert db_code == code

    # psycopg2 вернёт Decimal — приводим к float для сравнения
    db_price = float(db_price_rub)
    assert db_price == pytest.approx(price_rub)

    # --- подготовка вызова HTTP API ---
    api_key = API_KEY or os.getenv("API_KEY")
    if not api_key:
        pytest.skip("API_KEY is not set in environment, cannot call protected API")

    base_url = os.getenv("API_BASE_URL", API_URL)
    url = f"{base_url}/api/v1/sku/{code}/price-history"

    try:
        resp = requests.get(
            url,
            headers={"X-API-Key": api_key},
            timeout=10,
        )
    except requests.RequestException as exc:
        pytest.skip(f"API not reachable at {url}: {exc}")

    # --- проверки ответа API ---
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"

    payload = resp.json()
    assert payload["code"] == code
    assert payload["total"] >= 1
    assert payload["items"], "API вернул пустой список items"

    # Эндпоинт сортирует по effective_from DESC, берём первую (самую свежую) запись
    latest_item = payload["items"][0]
    api_price = float(latest_item["price_rub"])

    # Сравниваем цену из API с ценой из product_prices
    assert api_price == pytest.approx(db_price)
