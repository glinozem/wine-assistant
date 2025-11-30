from __future__ import annotations

"""
Сверка поставщиков между:
  - Excel: data/catalog/wineries_enrichment_from_pdf.xlsx
  - БД: SELECT DISTINCT supplier FROM products

Цели:
  - Показать, какие supplier_key из Excel отсутствуют в products.supplier.
  - Какие поставщики есть в products, но пока отсутствуют в Excel.
  - Подсказать возможные "похожие" пары имён, чтобы ты мог руками поправить Excel.
"""

import argparse
from pathlib import Path
from typing import List, Set, Tuple

import pandas as pd
from dotenv import load_dotenv

from scripts.load_utils import get_conn  # уже есть в проекте

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
EXCEL_PATH = Path("data/catalog/wineries_enrichment_from_pdf_norm.xlsx")


def load_excel_suppliers(path: Path) -> Set[str]:
    df = pd.read_excel(path)
    suppliers = (
        df["supplier_key"]
        .dropna()
        .astype(str)
        .map(str.strip)
    )
    return set(suppliers)


def load_db_suppliers() -> Set[str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT supplier FROM products;")
            rows = cur.fetchall()
    suppliers = { (row[0] or "").strip() for row in rows }
    return suppliers


def normalize_name(name: str) -> str:
    """
    Очень грубая нормализация для поиска похожих имён:
    - lower()
    - убираем слова типа 'maison', 'estate', 'fattoria', 'v8+', 'co.'
    - убираем пунктуацию, лишние пробелы
    """
    import re

    n = name.lower()
    n = n.replace("–", "-")  # длинное тире
    n = re.sub(r"[\"'.,]", " ", n)
    # выкинем самые типичные "служебные" слова
    for token in [
        "maison",
        "weingut",
        "fattoria",
        "estate",
        "v8+",
        "co",
        "s.s.",
        "società agricola",
        "societa agricola",
    ]:
        n = n.replace(token, " ")
    n = " ".join(n.split())
    return n


def build_similarity_suggestions(
    only_excel: Set[str], only_db: Set[str]
) -> List[Tuple[str, List[str]]]:
    """
    Для каждого supplier из Excel, которого нет в БД,
    пытаемся найти "похожие" имена в БД по нормализованной форме:
      - совпадение по подстроке после normalize_name()
    Это подсказки, не автоматика.
    """
    norm_db = {name: normalize_name(name) for name in only_db}
    suggestions: List[Tuple[str, List[str]]] = []

    for ex in only_excel:
        ne = normalize_name(ex)
        candidates = []
        for db_name, ndb in norm_db.items():
            if not ne or not ndb:
                continue
            if ne in ndb or ndb in ne:
                candidates.append(db_name)
        if candidates:
            suggestions.append((ex, sorted(candidates)))
    return suggestions


def main() -> None:
    print(f"[+] Читаем Excel: {EXCEL_PATH}")
    excel_suppliers = load_excel_suppliers(EXCEL_PATH)
    print(f"    Поставщиков в Excel: {len(excel_suppliers)}")

    print("[+] Читаем поставщиков из products...")
    db_suppliers = load_db_suppliers()
    print(f"    Поставщиков в БД: {len(db_suppliers)}")

    only_in_excel = sorted(excel_suppliers - db_suppliers)
    only_in_db = sorted(db_suppliers - excel_suppliers)

    print("\n=== Поставщики, которые есть в Excel, но НЕТ в products.supplier ===")
    if not only_in_excel:
        print("  (пусто)")
    else:
        for name in only_in_excel:
            print("  -", name)

    print("\n=== Поставщики, которые есть в products.supplier, но НЕТ в Excel ===")
    if not only_in_db:
        print("  (пусто)")
    else:
        for name in only_in_db:
            print("  -", name)

    print("\n=== Подсказки по возможному соответствию имён ===")
    suggestions = build_similarity_suggestions(set(only_in_excel), set(only_in_db))
    if not suggestions:
        print("  (ничего подозрительного не нашли)")
    else:
        for ex_name, db_candidates in suggestions:
            print(f"  Excel: {ex_name}")
            for cand in db_candidates:
                print(f"    ↳ Похож на: {cand}")
            print()


if __name__ == "__main__":
    main()
