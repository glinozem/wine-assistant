from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from etl.run_daily import run_etl


def import_with_run_daily(
    conn,  # conn пока не используется, но интерфейс единый
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
    # ВАЖНО: run_etl сейчас управляет импортом самостоятельно.
    # Если он не использует conn — ок, но orchestrator всё равно
    # ведёт registry + обработку статуса.
    res = run_etl(xlsx_path=file_path, sheet=sheet, mapping_path=mapping_path)

    # Нормализуем вывод под orchestrator/registry
    return {
        "metrics": res.get("metrics", {}) if isinstance(res, dict) else {},
        "artifact_paths": res.get("artifact_paths", {}) if isinstance(res, dict) else {},
        "envelope_id": res.get("envelope_id") if isinstance(res, dict) else None,
    }
