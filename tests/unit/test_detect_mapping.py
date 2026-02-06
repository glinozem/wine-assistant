import pandas as pd

from etl.run_daily import detect_mapping


def test_detect_mapping_heuristic_maps_multiple_fields():
    df = pd.DataFrame(columns=["Код товара", "Цена, руб", "Остаток"])
    mapping = detect_mapping(df, mapping_template={})
    # До фикса баг возвращал маппинг после первого tgt (обычно только code)
    assert "code" in mapping
    assert "price_rub" in mapping or "price_list_rub" in mapping or "price_final_rub" in mapping
    assert "stock_total" in mapping


def test_detect_mapping_template_takes_priority_when_complete():
    df = pd.DataFrame(columns=["SKU", "PRICE"])
    template = {"mapping": {"code": "SKU", "price_rub": "PRICE"}}
    mapping = detect_mapping(df, template)
    assert mapping == {"code": "SKU", "price_rub": "PRICE"}
