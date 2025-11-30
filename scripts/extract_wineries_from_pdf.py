from __future__ import annotations

"""
Извлечение данных о винодельнях из PDF-каталога DW 2025
в Excel-файл формата, совместимого с load_wineries.py.

Выходной Excel будет содержать колонки:

    supplier_key
    supplier_key_ru
    region
    producer_site
    winery_description_ru
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from PyPDF2 import PdfReader  # при необходимости: pip install PyPDF2

PDF_PATH = Path("data/catalog/Каталог DW 2025.pdf")
OUT_XLSX = Path("data/catalog/wineries_enrichment_from_pdf.xlsx")


def normalize_spaces(text: str) -> str:
    """Убираем дубли пробелов/переносов, выравниваем текст."""
    text = text.replace("\r", "\n")
    # иногда в каталоге стоит "Pinot -Chevauchet" → убираем пробелы вокруг дефиса
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"[ \t]+", " ", text)
    # оставляем двойные переводы как разделители абзацев
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_producer_page(raw_text: str, page_number: int) -> Optional[Dict[str, str]]:
    """
    Парсим страницу, если на ней есть строка 'Производитель'.
    Возвращаем dict для одной винодельни или None.
    """
    if "Производитель" not in raw_text:
        return None

    text = normalize_spaces(raw_text)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # --- 1. Ищем строку с производителем ---
    header_line = None
    for line in lines:
        if line.startswith("Производитель"):
            header_line = line
            break

    if not header_line:
        return None

    # Убираем префикс "Производитель" + ":" и берём только тело
    body = re.sub(r"^Производитель\s*:?\s*", "", header_line).strip()

    supplier_key: Optional[str] = None
    supplier_key_ru: Optional[str] = None

    # Вариант 1: "Weingut Rudolf Rabl / Жан Перье" или "Weingut Rudolf Rabl /"
    if "/" in body:
        left, right = body.split("/", 1)
        supplier_key = left.strip() or None
        supplier_key_ru = right.strip() or None

    # Вариант 2: "Mangup Estate , Усадьба Мангуп"
    elif "," in body:
        left, right = body.split(",", 1)
        supplier_key = left.strip() or None
        supplier_key_ru = right.strip() or None

    # Вариант 3: "Минский завод игристых вин (МЗИВ)" (только одно имя)
    else:
        supplier_key = body or None
        supplier_key_ru = None

    if not supplier_key:
        print(f"[WARN] Не удалось распарсить Производитель на стр. {page_number}: {header_line}")
        return None

    producer_site: Optional[str] = None
    region: Optional[str] = None

    # --- 2. Ищем сайт и регион ---
    for line in lines:
        # Сайт: www.vins-perrier.com / "Сайт: https://www.cattin.fr"
        if line.startswith("Сайт"):
            site = re.sub(r"^Сайт\s*:?", "", line).strip()
            producer_site = site or None

        # "Регион: Savoie / Савойя" или "Регион Ланкедок Долина Роны , Прованс , Бордо"
        if line.startswith("Регион"):
            tmp = re.sub(r"^Регион\s*:?", "", line).strip()
            tmp = tmp.replace(" ,", ",")
            region = tmp or None

    # --- 3. Описание винодельни (русский текст) ---
    meta_prefixes = (
        "Сайт", "Владелец", "Виноделы", "Виноградники",
        "Регион", "Зона", "Адрес", "Тип винодельни",
        "Страна", "Линейка"
    )

    try:
        idx_header = lines.index(header_line)
    except ValueError:
        idx_header = 0

    desc_lines: List[str] = []
    meta_block_ended = False

    for line in lines[idx_header + 1:]:
        if not meta_block_ended:
            # Пока идёт блок "Сайт/Регион/..." — пропускаем
            if any(line.startswith(p) for p in meta_prefixes):
                continue
            if not line:
                continue
            meta_block_ended = True

        desc_lines.append(line)

    winery_description_ru = " ".join(desc_lines).strip() or None

    max_len = 3000
    if winery_description_ru and len(winery_description_ru) > max_len:
        winery_description_ru = winery_description_ru[:max_len].rstrip() + "…"

    return {
        "supplier_key": supplier_key,
        "supplier_key_ru": supplier_key_ru,
        "region": region,
        "producer_site": producer_site,
        "winery_description_ru": winery_description_ru,
        "_page": page_number,
    }


def extract_wineries(pdf_path: Path) -> List[Dict[str, str]]:
    reader = PdfReader(str(pdf_path))
    records: List[Dict[str, str]] = []

    for i, page in enumerate(reader.pages):
        raw_text = page.extract_text() or ""
        rec = parse_producer_page(raw_text, page_number=i + 1)
        if rec:
            records.append(rec)

    return records


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF не найден: {PDF_PATH}")

    records = extract_wineries(PDF_PATH)
    print(f"Найдено виноделен в PDF: {len(records)}")

    if not records:
        print("Ничего не найдено. Проверь файл/кодировку/поиск 'Производитель'.")
        return

    # Преобразуем в DataFrame
    df = pd.DataFrame(records)

    # Основной выход — без служебной колонки _page
    df_out = df[[
        "supplier_key",
        "supplier_key_ru",
        "region",
        "producer_site",
        "winery_description_ru",
    ]]

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_excel(OUT_XLSX, index=False)
    print(f"Сохранено {len(df_out)} записей в {OUT_XLSX}")

    # На всякий случай можно сохранить и с _page для отладки:
    debug_path = OUT_XLSX.with_name(OUT_XLSX.stem + "_debug.xlsx")
    df.to_excel(debug_path, index=False)
    print(f"(Отладочная версия с колонкой _page сохранена в {debug_path})")


if __name__ == "__main__":
    main()
