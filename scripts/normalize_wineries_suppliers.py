from __future__ import annotations

"""
Нормализация supplier_key в wineries_enrichment_from_pdf.xlsx
под точные имена из products.supplier.

Берём готовую маппинг-таблицу:
    "ALAZANI"                      -> "Alazani"
    "Bodegas Delampa"              -> "Bodegas Delampa, S.L."
    "Bodegas Lopez Morenas"        -> "Lopez Morenas"
    "Castellari Bergaglio"         -> "Bergaglio"
    "Chiaromonte"                  -> "Tenute Chiaromonte"
    "Corte Alta Fumane"            -> "Corte Alta"
    "De Wetshof"                   -> "De Wetshof Estate"
    "Fattoria Giuseppe Savini"     -> "Savini"
    "Garage Wine Co."              -> "Garage Wine"
    "Lake Road – Origin Wine"      -> "Lake Road - Origin Wine"
    "Maison Joseph Cattin"         -> "Cattin"
    "V8+ Genagricola"              -> "Genagricola SpA"
    "Weingut Rudolf Rabl"          -> "Rabl"
    "Weinhaus Gebruder Steffen"    -> "Gebruder Steffen"
    "Бодегас Милениум"             -> "Bodegas Millenium"
    "Минский завод игристых вин (МЗИВ)" -> "МЗИВ"
    "Mangup Estate"                -> "Мангуп"
    "Château Paradis"              -> "Chateau Paradis"
"""

from pathlib import Path
from typing import Dict

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_XLSX = BASE_DIR / "data" / "catalog" / "wineries_enrichment_from_pdf.xlsx"
DST_XLSX = BASE_DIR / "data" / "catalog" / "wineries_enrichment_from_pdf_norm.xlsx"


MAPPING: Dict[str, str] = {
    "ALAZANI": "Alazani",
    "Bodegas Delampa": "Bodegas Delampa, S.L.",
    "Bodegas Lopez Morenas": "Lopez Morenas",
    "Castellari Bergaglio": "Bergaglio",
    "Chiaromonte": "Tenute Chiaromonte",
    "Corte Alta Fumane": "Corte Alta",
    "De Wetshof": "De Wetshof Estate",
    "Fattoria Giuseppe Savini": "Savini",
    "Garage Wine Co.": "Garage Wine",
    "Lake Road – Origin Wine": "Lake Road - Origin Wine",  # длинное тире -> обычный дефис
    "Maison Joseph Cattin": "Cattin",
    "V8+ Genagricola": "Genagricola SpA",
    "Weingut Rudolf Rabl": "Rabl",
    "Weinhaus Gebruder Steffen": "Gebruder Steffen",
    "Бодегас Милениум": "Bodegas Millenium",
    "Минский завод игристых вин (МЗИВ)": "МЗИВ",
    "Mangup Estate": "Мангуп",
    "Château Paradis": "Chateau Paradis",
}


def main() -> None:
    if not SRC_XLSX.exists():
        raise FileNotFoundError(f"Не найден исходный Excel: {SRC_XLSX}")

    print(f"[+] Читаем {SRC_XLSX}")
    df = pd.read_excel(SRC_XLSX)

    if "supplier_key" not in df.columns:
        raise KeyError("В Excel нет колонки 'supplier_key'")

    # нормализуем пробелы + сопоставляем по точному тексту
    def normalize_value(val: object) -> object:
        if not isinstance(val, str):
            return val
        v = val.strip()
        # сначала пробуем заменить по словарю
        if v in MAPPING:
            print(f"  [MAP] '{v}' -> '{MAPPING[v]}'")
            return MAPPING[v]
        return v

    df["supplier_key"] = df["supplier_key"].map(normalize_value)

    print(f"[+] Сохраняем результат в {DST_XLSX}")
    df.to_excel(DST_XLSX, index=False)
    print("[OK] Готово")


if __name__ == "__main__":
    main()
