from __future__ import annotations

"""
Загрузка/обновление справочника виноделен (wineries) из Excel-файла
data/catalog/wineries_enrichment.xlsx.

Ожидаемые колонки в Excel:

    supplier_key           - ключ винодельни, совпадает с products.supplier
    supplier_key_ru        - имя винодельни на русском
    region                 - регион (строкой)
    producer_site          - сайт (URL или домен)
    winery_description_ru  - описание винодельни на русском

Использование:

    # DRY-RUN — только показать, что будет сделано
    python -m scripts.load_wineries --excel ".\\data\\catalog\\wineries_enrichment.xlsx"

    # Реальная загрузка/обновление в БД
    python -m scripts.load_wineries --excel ".\\data\\catalog\\wineries_enrichment.xlsx" --apply
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

from scripts.load_utils import get_conn

load_dotenv()

REQUIRED_COLUMNS = [
    "supplier_key",
    "supplier_key_ru",
    "region",
    "producer_site",
    "winery_description_ru",
]


def load_excel(path: Path) -> List[Dict[str, Any]]:
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

    # NaN -> None
    df = df.where(pd.notna(df), None)

    # Лёгкая нормализация пробелов в текстовых полях
    for col in ["supplier_key", "supplier_key_ru", "region", "producer_site", "winery_description_ru"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: " ".join(str(v).split()) if isinstance(v, str) else v
            )

    records: List[Dict[str, Any]] = df.to_dict(orient="records")
    return records


def dry_run(records: List[Dict[str, Any]]) -> None:
    print(f"Загружено записей виноделен из Excel: {len(records)}\n")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for rec in records:
                supplier = rec.get("supplier_key")
                if not supplier:
                    continue

                cur.execute(
                    """
                    SELECT id, supplier, supplier_ru, region, producer_site
                      FROM wineries
                     WHERE supplier = %s
                    """,
                    (supplier,),
                )
                row = cur.fetchone()

                if row is None:
                    print(f"[NEW]   supplier={supplier!r} будет ДОБАВЛЕН в таблицу wineries")
                else:
                    print(f"[EXIST] supplier={supplier!r} уже есть (id={row[0]})")

                print(
                    f"        supplier_ru={rec.get('supplier_key_ru')!r}, "
                    f"region={rec.get('region')!r}, "
                    f"site={rec.get('producer_site')!r}"
                )
                print()
    finally:
        conn.close()


def apply(records: List[Dict[str, Any]]) -> None:
    conn = get_conn()
    conn.autocommit = False

    inserted = 0
    updated = 0

    try:
        with conn.cursor() as cur:
            for rec in records:
                supplier: Optional[str] = rec.get("supplier_key")
                supplier_ru: Optional[str] = rec.get("supplier_key_ru")
                region: Optional[str] = rec.get("region")
                site: Optional[str] = rec.get("producer_site")
                desc_ru: Optional[str] = rec.get("winery_description_ru")

                if not supplier:
                    continue

                cur.execute(
                    """
                    INSERT INTO wineries (supplier, supplier_ru, region, producer_site, description_ru)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (supplier) DO UPDATE
                    SET
                        supplier_ru    = EXCLUDED.supplier_ru,
                        region         = EXCLUDED.region,
                        producer_site  = EXCLUDED.producer_site,
                        description_ru = EXCLUDED.description_ru,
                        updated_at     = now()
                    RETURNING (xmax = 0) AS inserted;
                    """,
                    (supplier, supplier_ru, region, site, desc_ru),
                )

                was_inserted = cur.fetchone()[0]
                if was_inserted:
                    inserted += 1
                    action = "INSERT"
                else:
                    updated += 1
                    action = "UPDATE"

                print(
                    f"[{action}] supplier={supplier!r}, "
                    f"supplier_ru={supplier_ru!r}, region={region!r}, site={site!r}"
                )

        conn.commit()
        print(
            f"\nГотово. Вставлено новых записей: {inserted}, "
            f"обновлено существующих: {updated}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Загрузка/обновление справочника виноделен (wineries) из Excel."
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
