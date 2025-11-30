"""
Обогащение products.producer_site и products.region
из файла wineries_enrichment.xlsx.

Режимы работы:

    # DRY-RUN: только показывает, что бы обновилось
    python -m scripts.enrich_producers --excel data/catalog/wineries_enrichment.xlsx

    # APPLY: реально применяет изменения к БД
    python -m scripts.enrich_producers --excel data/catalog/wineries_enrichment.xlsx --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

from scripts.load_utils import get_conn

load_dotenv()

REQUIRED_COLUMNS = [
    "supplier_key",
    "producer_site",
    "winery_description_ru",
]

OPTIONAL_COLUMNS = [
    "supplier_key_ru",
    "region",
]


def load_excel(path: Path) -> List[Dict[str, Any]]:
    """Чтение Excel в список словарей."""
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Файл {path} не содержит обязательные колонки: {missing}. "
            f"Фактические: {list(df.columns)}"
        )

    df = df.where(pd.notna(df), None)
    records: List[Dict[str, Any]] = df.to_dict(orient="records")
    return records


def dry_run(records: List[Dict[str, Any]]) -> None:
    """DRY-RUN: показываем, сколько строк может быть обогащено по site и по region."""
    print(f"Загружено записей виноделен: {len(records)}\n")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for rec in records:
                supplier = rec.get("supplier_key")
                site = rec.get("producer_site")
                region_val = rec.get("region")

                if not supplier:
                    continue
                if not site and not region_val:
                    # Нечего обогащать
                    continue

                print(f"supplier = {supplier!r}")

                if site:
                    cur.execute(
                        """
                        SELECT count(*) FROM products
                        WHERE supplier = %s
                          AND (producer_site IS NULL OR producer_site = '')
                        """,
                        (supplier,),
                    )
                    count_site = cur.fetchone()[0]
                    print(
                        f"  [site]   producer_site -> {site!r}, "
                        f"строк с пустым producer_site: {count_site}"
                    )
                else:
                    print("  [site]   пропущено (нет значения в Excel)")

                if region_val:
                    cur.execute(
                        """
                        SELECT count(*) FROM products
                        WHERE supplier = %s
                          AND (region IS NULL OR region = '')
                        """,
                        (supplier,),
                    )
                    count_region = cur.fetchone()[0]
                    print(
                        f"  [region] region -> {region_val!r}, "
                        f"строк с пустым region: {count_region}"
                    )
                else:
                    print("  [region] пропущено (нет значения в Excel)")

                print()

    finally:
        conn.close()


def apply(records: List[Dict[str, Any]]) -> None:
    """Применить изменения к базе: заполнить producer_site и/или region, если они пустые."""
    conn = get_conn()
    conn.autocommit = False

    try:
        total_rows = 0

        with conn.cursor() as cur:
            for rec in records:
                supplier = rec.get("supplier_key")
                site = rec.get("producer_site")
                region_val = rec.get("region")

                if not supplier:
                    continue
                if not site and not region_val:
                    # Нечего обновлять
                    continue

                # Обновляем ТОЛЬКО там, где соответствующее поле пустое
                sql = """
                    UPDATE products
                    SET
                        producer_site = CASE
                            WHEN %(site)s IS NOT NULL
                                 AND (producer_site IS NULL OR producer_site = '')
                            THEN %(site)s
                            ELSE producer_site
                        END,
                        region = CASE
                            WHEN %(region)s IS NOT NULL
                                 AND (region IS NULL OR region = '')
                            THEN %(region)s
                            ELSE region
                        END
                    WHERE supplier = %(supplier)s
                """

                params = {
                    "site": site,
                    "region": region_val,
                    "supplier": supplier,
                }

                cur.execute(sql, params)
                updated = cur.rowcount
                total_rows += updated

                print(
                    f"[APPLY] supplier={supplier!r}: "
                    f"обновлено строк (по совокупности полей) = {updated}, "
                    f"site={site!r}, region={region_val!r}"
                )

        conn.commit()
        print(f"\nГотово. Всего затронуто строк в products: {total_rows}")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Обогащение products.producer_site и products.region "
                    "данными из wineries_enrichment.xlsx."
    )
    parser.add_argument(
        "--excel",
        required=True,
        help="Путь к файлу wineries_enrichment.xlsx",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения в БД (по умолчанию только DRY-RUN).",
    )

    args = parser.parse_args()
    path = Path(args.excel)

    records = load_excel(path)

    if not args.apply:
        dry_run(records)
    else:
        apply(records)


if __name__ == "__main__":
    main()
