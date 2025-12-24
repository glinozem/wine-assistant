from __future__ import annotations

import os

import psycopg2


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v not in (None, "") else default


def connect_postgres(*, connect_timeout: int = 5) -> psycopg2.extensions.connection:
    """
    Connection helper consistent with tests/conftest.py defaults.
    Env priority:
      DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
      then PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE
    """
    host = _env("DB_HOST", _env("PGHOST", "127.0.0.1"))
    port = int(_env("DB_PORT", _env("PGPORT", "15432")))
    user = _env("DB_USER", _env("PGUSER", "postgres"))
    password = _env("DB_PASSWORD", _env("PGPASSWORD", "postgres"))
    dbname = _env("DB_NAME", _env("PGDATABASE", "wine_db"))

    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        connect_timeout=connect_timeout,
    )
    conn.autocommit = False
    return conn
