import hashlib
import os
import sys
import uuid
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

import pytest
import requests

from scripts.load_csv import main as load_csv_main
from scripts.load_utils import get_conn

# Такой же флаг, как и в tests/unit/test_load_utils.py
RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"

API_URL = os.getenv("API_URL", "http://localhost:18000")
API_KEY = os.getenv("API_KEY")


def _load_db_price_history(code: str) -> list[dict]:
    """
    Читает историю цен по SKU из product_prices и приводит к нормализованному виду.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code,
                       price_rub,
                       effective_from,
                       effective_to
                  FROM product_prices
                 WHERE code = %s
                 ORDER BY effective_from DESC
                """,
                (code,),
            )
            rows = cur.fetchall()

    history: list[dict] = []
    for db_code, price_rub, eff_from, eff_to in rows:
        assert db_code == code
        history.append(
            {
                "code": db_code,
                "price_rub": float(price_rub),
                "effective_from": eff_from.date()
                if hasattr(eff_from, "date")
                else eff_from,
                "effective_to": eff_to.date()
                if eff_to is not None and hasattr(eff_to, "date")
                else None,
            }
        )
    return history


def _load_api_price_history(
    code: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict]:
    """
    Дёргает /api/v1/sku/<code>/price-history, парсит JSON и приводит
    items к тому же формату, что и _load_db_price_history().
    """
    if api_key is None:
        api_key = os.getenv("API_KEY")
    if not api_key:
        pytest.skip("API_KEY is not set in environment, cannot call protected API")

    if base_url is None:
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

    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"

    payload = resp.json()
    assert payload["code"] == code
    assert payload["items"], "API вернул пустой список items"
    assert payload["total"] == len(payload["items"])

    def parse_http_date(value: str | None):
        """
        Преобразует RFC1123-текст вроде 'Tue, 03 Jun 2025 00:00:00 GMT' в date().
        """
        if not value:
            return None
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").date()

    history: list[dict] = []
    for item in payload["items"]:
        history.append(
            {
                "code": item.get("code", code),
                "price_rub": float(item["price_rub"]),
                "effective_from": parse_http_date(item["effective_from"]),
                "effective_to": parse_http_date(item.get("effective_to")),
            }
        )

    return history


def _assert_price_histories_equal(
    code: str,
    db_history: list[dict],
    api_history: list[dict],
) -> None:
    """
    Сравнивает истории из БД и API как два списка словарей.
    Порядок не важен: сортируем по (effective_from, effective_to, price_rub).
    """
    assert db_history, f"DB history is empty for code={code}"
    assert api_history, f"API history is empty for code={code}"
    assert len(api_history) == len(
        db_history
    ), f"DB and API histories have different lengths for code={code}"

    def sort_key(h: dict):
        return (
            h["effective_from"],
            h["effective_to"] or date_cls.max,
            round(h["price_rub"], 4),
        )

    db_sorted = sorted(db_history, key=sort_key)
    api_sorted = sorted(api_history, key=sort_key)

    for db_item, api_item in zip(db_sorted, api_sorted):
        assert api_item["code"] == code
        assert api_item["effective_from"] == db_item["effective_from"]
        assert api_item["effective_to"] == db_item["effective_to"]
        assert api_item["price_rub"] == pytest.approx(
            db_item["price_rub"]
        ), f"Цена из API не совпадает с ценой в product_prices для code={code}"


def _compute_sha256(path: Path) -> str:
    """Локальный helper для SHA256, чтобы найти наш файл в ingest_envelope."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _fetch_db_latest_price_for_sku(code: str) -> float:
    """
    Достаём самую свежую цену из product_prices по коду SKU.

    Берём запись с максимальным effective_from.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT price_rub
                  FROM product_prices
                 WHERE code = %s
                 ORDER BY effective_from DESC
                 LIMIT 1
                """,
                (code,),
            )
            row = cur.fetchone()

    assert row is not None, f"No product_prices row found for code={code}"
    (price_rub,) = row
    return float(price_rub)


def _fetch_api_latest_price_for_sku(code: str) -> float:
    """
    Достаём текущую цену из эндпоинта /api/v1/sku/<code>.

    Сейчас API отдаёт цену в поле ``price_final_rub``.
    На всякий случай поддерживаем и старую схему с ``price_rub``.
    """
    api_key = API_KEY or os.getenv("API_KEY")
    if not api_key:
        pytest.skip("API_KEY is not set in environment, cannot call protected API")

    base_url = os.getenv("API_BASE_URL", API_URL)
    url = f"{base_url}/api/v1/sku/{code}"

    try:
        resp = requests.get(
            url,
            headers={"X-API-Key": api_key},
            timeout=10,
        )
    except requests.RequestException as exc:
        pytest.skip(f"API not reachable at {url}: {exc}")

    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"

    payload = resp.json()
    assert payload["code"] == code

    if "price_final_rub" in payload:
        raw_price = payload["price_final_rub"]
    elif "price_rub" in payload:
        raw_price = payload["price_rub"]
    else:
        pytest.fail("API payload has no 'price_final_rub' or 'price_rub' field")

    return float(raw_price)


def _assert_latest_price_db_and_api_consistent(code: str) -> None:
    """
    Универсальный helper: сравнивает самую свежую цену в БД и в /api/v1/sku/<code>.
    """
    db_price = _fetch_db_latest_price_for_sku(code)
    api_price = _fetch_api_latest_price_for_sku(code)

    assert api_price == pytest.approx(
        db_price
    ), f"Latest price mismatch for {code}: db={db_price}, api={api_price}"


# =============================================================================
# E2E: базовые сценарии ETL
# =============================================================================


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
    """
    code = f"INTTEST_SMOKE_{uuid.uuid4().hex[:8]}"

    csv_path: Path = tmp_path / "test_price.csv"
    csv_path.write_text(f"Код;Цена\n{code};123.45\n", encoding="utf-8")

    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
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
      * в products есть строка с этим кодом и хоть одно ценовое поле заполнено
    """
    code = f"INTTEST_ETL_{uuid.uuid4().hex[:8]}"
    csv_path: Path = tmp_path / "test_price_persist.csv"
    csv_path.write_text(f"Код;Цена\n{code};123.45\n", encoding="utf-8")

    file_hash = _compute_sha256(csv_path)

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

    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    with get_conn() as conn:
        with conn.cursor() as cur:
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

            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after = cur.fetchone()[0]
            assert prices_after >= prices_before + 1

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
            assert any(
                p is not None
                for p in (price_rub, price_list_rub, price_final_rub)
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


# =============================================================================
# /price-history: сквозные тесты
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_price_import_db_and_api_price_history(tmp_path):
    """
    Упрощённый сквозной тест для эндпоинта /price-history.
    """
    code = f"INTTEST_API_{uuid.uuid4().hex[:8]}"
    price_str = "123.45"

    csv_path: Path = tmp_path / "test_price_api_smoke.csv"
    csv_path.write_text(f"Код;Цена\n{code};{price_str}\n", encoding="utf-8")

    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            prices_after = cur.fetchone()[0]
            assert prices_after >= 1, "Ожидаем хотя бы одну запись в product_prices"

    api_history = _load_api_price_history(code)
    assert len(api_history) >= 1, "API вернул пустую историю цен"


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_price_import_price_history_api_matches_db(tmp_path):
    """
    Сквозной интеграционный тест «толстого» сценария:

    1. Готовит несколько CSV-файлов с одним SKU, разными датами и ценами.
    2. Для каждого файла запускает ETL через load_csv_main().
    3. Читает полную историю этого SKU из product_prices.
    4. Дёргает /api/v1/sku/<code>/price-history.
    5. Сравнивает, что история из API == истории в БД.
    """
    code = f"INTTEST_API_{uuid.uuid4().hex[:8]}"

    price_scenarios = [
        ("2025_01_20", 100.0),
        ("2025_02_15", 110.0),
        ("2025_03_10", 120.0),
    ]

    # --- 1–2. Несколько запусков ETL с разными датами ---
    for date_tag, price_rub in price_scenarios:
        csv_path: Path = tmp_path / f"{date_tag}_test_price_history.csv"
        csv_path.write_text(
            "Код;Цена\n"
            f"{code};{price_rub}\n",
            encoding="utf-8",
        )
        sys.argv = ["load_csv.py", "--csv", str(csv_path)]
        load_csv_main()

    # --- 3. История из БД ---
    db_history = _load_db_price_history(code)
    assert db_history, "Ожидаем, что в product_prices есть записи по этому SKU"
    assert len(db_history) == len(
        price_scenarios
    ), "Ожидаем по одному шагу цены на каждый загруженный прайс"

    # --- 4. История из API ---
    api_history = _load_api_price_history(code)

    # --- 5. Сравнение ---
    _assert_price_histories_equal(code, db_history, api_history)


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_price_import_db_and_api_consistent_for_real_skus():
    """
    Мониторинговый тест: проверяет, что для нескольких реальных SKU
    история цен, отдаваемая /api/v1/sku/<code>/price-history,
    совпадает с данными в product_prices.
    """
    real_codes = ["D000081", "D009704"]

    for code in real_codes:
        db_history = _load_db_price_history(code)
        if not db_history:
            pytest.skip(
                f"No rows in product_prices for code={code!r}. "
                "Looks like real data is not loaded in this environment."
            )

        api_history = _load_api_price_history(code)
        _assert_price_histories_equal(code, db_history, api_history)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason=(
        "Requires running PostgreSQL and HTTP API, "
        "and preloaded real price history data"
    ),
)
@pytest.mark.parametrize("code", ["D000081", "D009704"])
def test_price_history_real_skus_db_and_api_consistent(code):
    """
    Более тяжёлый мониторинговый тест: та же проверка, что и выше,
    но размеченный как slow и параметризованный по SKU.
    """
    db_history = _load_db_price_history(code)
    if not db_history:
        pytest.skip(
            f"No rows in product_prices for code={code!r}. "
            "Looks like real data is not loaded in this environment."
        )

    api_history = _load_api_price_history(code)
    _assert_price_histories_equal(code, db_history, api_history)


# =============================================================================
# Single latest price: /api/v1/sku/<code>
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
def test_latest_price_single_sku_db_and_api_consistent(tmp_path):
    """
    Сквозной тест для single latest price:

    1. Готовит CSV с одним SKU и ценой.
    2. Запускает ETL (load_csv_main).
    3. Проверяет, что в product_prices появилась запись.
    4. Сравнивает самую свежую цену в product_prices и в /api/v1/sku/<code>.
    """
    code = f"INTTEST_LATEST_{uuid.uuid4().hex[:8]}"
    price_rub = 123.45

    csv_path: Path = tmp_path / "test_latest_price_single_sku.csv"
    csv_path.write_text(
        "Код;Цена\n"
        f"{code};{price_rub}\n",
        encoding="utf-8",
    )

    # Запускаем ETL
    sys.argv = ["load_csv.py", "--csv", str(csv_path)]
    load_csv_main()

    # На всякий случай убедимся, что в product_prices что-то появилось
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM product_prices WHERE code = %s",
                (code,),
            )
            cnt = cur.fetchone()[0]
            assert cnt >= 1, "Expected at least one row in product_prices"

    # А дальше — просто сравниваем latest price в БД и в API
    _assert_latest_price_db_and_api_consistent(code)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="Requires running PostgreSQL, API and RUN_DB_TESTS=1",
)
@pytest.mark.parametrize("code", ["D000081", "D009704"])
def test_latest_price_real_skus_db_and_api_consistent(code):
    """
    Мониторинговый тест на реальных кодах из боевых прайсов.

    Проверяет, что текущая цена в /api/v1/sku/<code>
    совпадает с последней записью в product_prices.
    """
    _assert_latest_price_db_and_api_consistent(code)
