# tests/integration/conftest.py
import os

import pytest

# База для интеграционных тестов: по умолчанию — локальный postgres из docker-compose
os.environ.setdefault("PGHOST", os.getenv("DB_HOST", "localhost"))
os.environ.setdefault("PGPORT", os.getenv("DB_PORT", "15432"))
os.environ.setdefault("PGDATABASE", os.getenv("DB_NAME", "wine_db"))
os.environ.setdefault("PGUSER", os.getenv("DB_USER", "postgres"))
os.environ.setdefault("PGPASSWORD", os.getenv("DB_PASSWORD", "postgres"))

# В интеграционных тестах не хотим упираться в rate limit
os.environ.setdefault("RATE_LIMIT_ENABLED", "0")


@pytest.fixture(autouse=True)
def _integration_env_sanity():
    """
    Автоматический fixture для интеграционных тестов.

    Сейчас он просто гарантирует, что переменные окружения выставлены до
    старта каждого теста. Если понадобится — сюда можно добавить дополнительные
    проверки/инициализацию.
    """
    yield
