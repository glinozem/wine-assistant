#!/usr/bin/env python3
"""Retention Policy — автоматическая очистка старых партиций product_prices.

Политика по умолчанию:
- хранить данные за последние 2 года (730 дней);
- удалять партиции старше этого порога;
- поддерживать DRY_RUN-режим для безопасного теста.

Ожидается запуск по расписанию (cron или отдельный job-контейнер), примерно так:

    # 1-го числа каждого месяца в 03:00
    0 3 1 * * cd /app && /app/.venv/bin/python /app/jobs/cleanup_old_partitions.py >> /var/log/retention_policy.log 2>&1
"""

import logging
import os
from datetime import datetime, timedelta

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "730"))  # по умолчанию 2 года
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def get_connection():
    """Создать подключение к Postgres, используя стандартные env-переменные."""
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        database=os.getenv("PGDATABASE", "wine_db"),
    )


def get_old_partitions(conn, cutoff_date):
    """Вернуть список имён партиций product_prices, полностью лежащих до cutoff_date.

    Для простоты используем соглашение об именах:
        product_prices_YYYY_qN

    и сравниваем год партиции с годом cutoff_date.
    При необходимости можно доработать парсинг pg_get_expr(relpartbound,...).
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            child.relname AS partition_name,
            pg_get_expr(child.relpartbound, child.oid) AS partition_range
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child  ON pg_inherits.inhrelid  = child.oid
        WHERE parent.relname = 'product_prices'
        ORDER BY child.relname;
        """
    )

    old = []
    cutoff_year = cutoff_date.year

    for partition_name, partition_range in cur.fetchall():
        if not partition_name.startswith("product_prices_"):
            continue

        parts = partition_name.split("_")
        if len(parts) < 3:
            continue

        try:
            year = int(parts[2])
        except ValueError:
            continue

        if year < cutoff_year:
            old.append(partition_name)

    return old


def drop_partition(conn, partition_name):
    """Удалить (detach + drop) одну партицию."""
    cur = conn.cursor()

    cur.execute(
        """
        SELECT pg_size_pretty(pg_total_relation_size(%s));
        """,
        (partition_name,),
    )
    size = cur.fetchone()[0]

    logger.info("📦 Partition: %s, size: %s", partition_name, size)

    if DRY_RUN:
        logger.info("🔍 DRY RUN: would drop %s", partition_name)
        return

    logger.info("🚮 Detaching and dropping partition %s", partition_name)
    cur.execute(f"ALTER TABLE product_prices DETACH PARTITION {partition_name};")
    cur.execute(f"DROP TABLE {partition_name};")
    conn.commit()
    logger.info("✅ Dropped partition: %s", partition_name)


def main():
    logger.info("🚀 Retention policy cleanup started")
    logger.info("📅 Retention period: %d days (~%.1f years)", RETENTION_DAYS, RETENTION_DAYS / 365.0)
    logger.info("🔍 DRY_RUN: %s", DRY_RUN)

    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    logger.info("🗓️ Cutoff date: %s", cutoff_date.date())

    conn = get_connection()
    try:
        old_partitions = get_old_partitions(conn, cutoff_date)
        if not old_partitions:
            logger.info("✅ No old partitions to cleanup")
            return

        logger.info("📦 Found %d old partitions to cleanup", len(old_partitions))
        for partition_name in old_partitions:
            drop_partition(conn, partition_name)

        logger.info("✅ Cleanup completed")
    except Exception as exc:  # noqa: BLE001
        logger.exception("❌ Error during retention cleanup: %s", exc)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
