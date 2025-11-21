import os
import sys
from typing import Callable, Iterator, Optional

import psycopg2
import psycopg2.errors  # noqa: F401  # useful in tests if you need specific PG errors
import pytest
from flask import Flask

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
    from api.app import app as flask_app  # noqa: WPS433 (import inside function is intentional)

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
    h = host or os.getenv("PGHOST", "127.0.0.1")
    p = int(port or os.getenv("PGPORT", "15432"))  # prefer local mapped port in dev/tests
    u = user or os.getenv("PGUSER", "postgres")
    pw = password or os.getenv("PGPASSWORD", "dev_local_pw")
    db = dbname or os.getenv("PGDATABASE", "wine_db")

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
            f"PostgreSQL is not available at {h}:{p} (db='{db}'). "
            f"Reason: {exc}"
        )


@pytest.fixture(scope="function")
def db_connection():
    """
    Function-scoped PostgreSQL connection with automatic rollback.

    По умолчанию подключаемся к 127.0.0.1:15432 (как в docker-compose маппинге),
    чтобы локальные тесты работали одинаково на Windows/macOS/Linux.

    Если БД недоступна, тест *пропускается* с понятным сообщением.
    """
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
