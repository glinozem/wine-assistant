from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from etl.run_daily import run_etl

DEFAULT_MAPPING = "etl/mapping_template.json"


def _read_mapping(mapping_path: str) -> dict:
    p = Path(mapping_path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def import_with_run_daily(
    conn,
    *,
    supplier: str,
    file_path: str,
    as_of_date,
    run_id: UUID,
    envelope_id: Optional[UUID] = None,
    sheet: Optional[str] = None,
    mapping_path: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    mapping_path = mapping_path or str(DEFAULT_MAPPING)
    mt = _read_mapping(mapping_path)

    sheet = sheet or mt.get("sheet") or mt.get("sheet_name")

    res = run_etl(
        xlsx_path=file_path,
        sheet=sheet,
        mapping_path=mapping_path,
        conn=conn,
        as_of_date=as_of_date,
    )

    raw_metrics = res.get("metrics", {}) if isinstance(res, dict) else {}
    metrics: Dict[str, int] = {}

    # Приводим legacy-ключи к допустимым колонкам import_runs
    # orchestrator whitelist: total_rows_processed, rows_skipped, new_sku_count, updated_sku_count, ...
    if "total_rows_processed" in raw_metrics:
        metrics["total_rows_processed"] = int(
            raw_metrics["total_rows_processed"])
    elif "processed_rows" in raw_metrics:
        metrics["total_rows_processed"] = int(raw_metrics["processed_rows"])

    if "rows_skipped" in raw_metrics:
        metrics["rows_skipped"] = int(raw_metrics["rows_skipped"])

    artifact_paths = res.get("artifact_paths", {}) if isinstance(res,
                                                                 dict) else {}
    out_envelope_id = res.get("envelope_id") if isinstance(res, dict) else None

    if not isinstance(artifact_paths, dict):
        artifact_paths = {}

    return {
        "metrics": metrics,  # <-- ВАЖНО: нормализованные метрики
        "artifact_paths": artifact_paths,
        "envelope_id": out_envelope_id,
    }
