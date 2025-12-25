import os
import sys
from typing import Callable, Iterator, Optional

import psycopg2
import psycopg2.errors  # noqa: F401  # useful in tests if you need specific PG errors
import pytest
from flask import Flask

# Optional: load variables from local .env for tests/cli runs (does not override shell/CI env)
try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    # python-dotenv is optional; tests can still run if env vars are provided by the shell/CI.
    pass

# -----------------------------------------------------------------------------
# Test bootstrap
# -----------------------------------------------------------------------------
# Ensure project root is importable (so `api.app` resolves the same way in tests)
PROJECT_ROOT = os.path.abspath(".")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# -----------------------------------------------------------------------------
# Flask app fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def app() -> Iterator[Flask]:
    """
    Session-scoped Flask application.

    ВАЖНО:
    - Импортируем модуль приложения внутри фикстуры (лениво), чтобы тесты,
      которые делают importlib.reload(api.app) с разными env, работали предсказуемо.
    """
    # Minimal, safe defaults for tests
    os.environ.setdefault("FLASK_ENV", "testing")
    os.environ.setdefault("RATE_LIMIT_ENABLED", "0")  # disable limiter by default in unit tests

    # Lazy import to avoid side effects at module import time
    from api.app import app as flask_app

    # Make sure testing flags are on
    flask_app.config.update(
        {
            "TESTING": True,
            "DEBUG": False,
        }
    )
    yield flask_app


@pytest.fixture(scope="function")
def client(app: Flask):
    """
    Function-scoped test client.

    Example:
        r = client.get('/health')
        assert r.status_code == 200
    """
    return app.test_client()


# -----------------------------------------------------------------------------
# Environment helpers
# -----------------------------------------------------------------------------
@pytest.fixture(scope="function")
def set_env(monkeypatch) -> Callable[[str, str], None]:
    """
    Helper to set environment variables in tests.

    Example:
        set_env("API_KEY", "test-key")
    """

    def _set(key: str, value: str) -> None:
        monkeypatch.setenv(key, value)

    return _set


@pytest.fixture(scope="function")
def with_rate_limiter_enabled(monkeypatch):
    """
    Temporarily enable rate limiter for a specific test.

    Example:
        def test_public_limits(client, with_rate_limiter_enabled):
            r = client.get("/health")
            ...
    """
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    # default in-memory storage to avoid external deps
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URL", "memory://")
    # keep headers to assert against
    monkeypatch.setenv("RATELIMIT_HEADERS_ENABLED", "true")
    yield


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v not in (None, "") else default


def pytest_configure(config):
    # register custom markers (works with --strict-markers)
    config.addinivalue_line("markers", "db: requires a running Postgres (enable with RUN_DB_TESTS=1)")


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_DB_TESTS") == "1":
        return
    skip_db = pytest.mark.skip(reason="DB tests are disabled. Set RUN_DB_TESTS=1 to enable.")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


# -----------------------------------------------------------------------------
# Database fixtures
# -----------------------------------------------------------------------------
def _pg_connect_or_skip(
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    dbname: Optional[str] = None,
    connect_timeout: int = 2,
):
    """
    Try to connect to Postgres or skip the test with a helpful message.
    """
    # Prefer DB_* (project-wide), fallback to PG* (libpq/psql conventions).
    h = host or _env("DB_HOST", _env("PGHOST", "127.0.0.1"))
    p = int(port or _env("DB_PORT", _env("PGPORT", "15432")))
    u = user or _env("DB_USER", _env("PGUSER", "postgres"))
    pw = password or _env("DB_PASSWORD", _env("PGPASSWORD", "postgres"))
    db = dbname or _env("DB_NAME", _env("PGDATABASE", "wine_db"))

    try:
        return psycopg2.connect(
            host=h,
            port=p,
            user=u,
            password=pw,
            dbname=db,
            connect_timeout=connect_timeout,
        )
    except psycopg2.OperationalError as exc:
        # If database isn't up, skip DB-bound tests instead of failing the whole suite.
        pytest.skip(
            f"PostgreSQL is not available at {h}:{p} (db='{db}'). Reason: {exc}")


@pytest.fixture(scope="function")
def db_connection():
    """
    Function-scoped PostgreSQL connection with automatic rollback.

    По умолчанию подключаемся к 127.0.0.1:15432 (как в docker-compose маппинге),
    чтобы локальные тесты работали одинаково на Windows/macOS/Linux.

    Если БД недоступна, тест *пропускается* с понятным сообщением.
    """
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("DB tests are disabled. Set RUN_DB_TESTS=1 to enable.")
    conn = _pg_connect_or_skip()
    # ensure isolation between tests
    conn.autocommit = False
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


@pytest.fixture(scope="function")
def db_cursor(db_connection):
    """
    Function-scoped DB cursor with auto-rollback.
    """
    cur = db_connection.cursor()
    try:
        yield cur
    finally:
        db_connection.rollback()
        cur.close()


# -----------------------------------------------------------------------------
# Test data cleanup (integration tests)
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def cleanup_integration_test_data():
    """
    Automatically cleanup test data after ALL integration tests complete.

    This fixture runs once per test session (after all tests finish).
    It removes all products with codes starting with 'INTTEST_' prefix.

    Only runs when RUN_DB_TESTS=1 (i.e., when integration tests are enabled).
    """
    # Setup: nothing to do before tests
    yield

    # Teardown: cleanup after all tests
    if os.getenv("RUN_DB_TESTS") != "1":
        # Integration tests were skipped, no cleanup needed
        return

    try:
        # Connect to database
        conn = _pg_connect_or_skip(connect_timeout=5)
        conn.autocommit = False

        cursor = conn.cursor()

        # Count test records before deletion
        cursor.execute("SELECT COUNT(*) FROM products WHERE code LIKE 'INTTEST_%'")
        count_before = cursor.fetchone()[0]

        if count_before == 0:
            print("\n✅ No test data to cleanup (INTTEST_* records)")
            conn.close()
            return

        print(f"\n🧹 Cleaning up {count_before} test records (INTTEST_* prefix)...")

        # Delete in correct order (respecting FK constraints)
        # ВАЖНО: Используем колонку 'code' (не 'sku_code')

        # 1. inventory_history (child table)
        cursor.execute("DELETE FROM inventory_history WHERE code LIKE 'INTTEST_%'")
        deleted_inv = cursor.rowcount

        # 2. product_prices (child table)
        cursor.execute("DELETE FROM product_prices WHERE code LIKE 'INTTEST_%'")
        deleted_prices = cursor.rowcount

        # 3. products (parent table)
        cursor.execute("DELETE FROM products WHERE code LIKE 'INTTEST_%'")
        deleted_products = cursor.rowcount

        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Test data cleaned up:")
        print(f"   - products: {deleted_products}")
        print(f"   - product_prices: {deleted_prices}")
        print(f"   - inventory_history: {deleted_inv}")

    except Exception as e:
        print(f"\n⚠️  Warning: Could not cleanup test data: {e}")
        print("   This is non-fatal. You can manually cleanup with:")
        print("   python scripts/cleanup_test_data.py --apply")


# -----------------------------------------------------------------------------
# Sample data fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def sample_product():
    """
    Example product dict for quick tests.
    """
    return {
        "code": "TEST001",
        "producer": "Test Winery",
        "title_ru": "Test Wine",
        "country": "Italy",
        "region": "Tuscany",
        "price_list_rub": 1000.0,
        "price_final_rub": 900.0,
    }


@pytest.fixture
def sample_csv_data():
    """
    Small CSV sample for ETL tests.
    """
    return (
        "code,producer,title_ru,price_rub\n"
        "TEST001,Test Winery,Test Wine,1000\n"
        "TEST002,Another Winery,Another Wine,1500\n"
    )
