"""
Загрузка и просмотр файла с описаниями виноделен (wineries_enrichment.xlsx).

Использование:
    python -m scripts.load_wineries_enrichment --excel data/catalog/wineries_enrichment.xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

# Обязательные поля, без них файл считаем некорректным
REQUIRED_COLUMNS = [
    "supplier_key",
    "producer_site",
    "winery_description_ru",
]

# Необязательные, но полезные поля
OPTIONAL_COLUMNS = [
    "supplier_key_ru",
    "region",
]


def load_enrichment_excel(path: Path) -> list[dict[str, Any]]:
    """Читает Excel и возвращает список словарей по строкам."""
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    # Читаем первый лист
    df = pd.read_excel(path)

    # Нормализуем имена колонок (обрежем пробелы)
    df.columns = [str(c).strip() for c in df.columns]

    # Проверяем, что обязательные колонки есть
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"В файле {path} нет обязательных колонок: {', '.join(missing)}.\n"
            f"Найденные колонки: {list(df.columns)}"
        )

    # Заменим NaN / NaT / прочие "дыры" на обычный Python None
    df = df.where(pd.notna(df), None)

    records: list[dict[str, Any]] = df.to_dict(orient="records")
    return records


def print_enrichment(records: list[dict[str, Any]]) -> None:
    """Красиво выводит список виноделен в консоль."""
    if not records:
        print("Нет записей для отображения.")
        return

    for idx, rec in enumerate(records, start=1):
        supplier_key = rec.get("supplier_key")
        supplier_key_ru = rec.get("supplier_key_ru")
        producer_site = rec.get("producer_site")
        region = rec.get("region")
        desc = rec.get("winery_description_ru")

        print(f"[{idx}] supplier_key={supplier_key!r}")
        if supplier_key_ru:
            print(f"    supplier_key_ru={supplier_key_ru!r}")
        if region:
            print(f"    region={region!r}")
        print(f"    producer_site={producer_site!r}")

        if desc:
            # Сожмём текст, чтобы не заливать консоль
            short = str(desc).strip().replace("\n", " ")
            if len(short) > 200:
                short = short[:200] + "..."
            print(f"    winery_description_ru={short!r}")
        print()  # пустая строка между записями


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Просмотр файла с описаниями виноделен (enrichment)."
    )
    parser.add_argument(
        "--excel",
        type=str,
        required=True,
        help="Путь к файлу wineries_enrichment.xlsx",
    )

    args = parser.parse_args()
    path = Path(args.excel)

    records = load_enrichment_excel(path)
    print_enrichment(records)


if __name__ == "__main__":
    main()
