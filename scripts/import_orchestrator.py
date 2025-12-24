from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional
from uuid import UUID

import psycopg2

from scripts.import_run_registry import ImportRunRegistry
from scripts.ingest_envelope import create_ingest_envelope_best_effort

logger = logging.getLogger(__name__)


ALLOWED_METRIC_COLUMNS = {
    "total_rows_processed",
    "new_sku_count",
    "updated_sku_count",
    "new_winery_count",
    "quarantine_count",
    "rows_skipped",
}


@dataclass(frozen=True)
class OrchestratorResult:
    status: str  # success | failed | skipped
    run_id: Optional[UUID] = None
    envelope_id: Optional[UUID] = None
    reason: Optional[str] = None


def load_callable(spec: str) -> Callable[..., Dict[str, Any]]:
    """
    spec format: "module.submodule:callable_name"
    """
    if ":" not in spec:
        raise ValueError("import function spec must be in 'module:callable' format")
    mod_name, fn_name = spec.split(":", 1)
    module = importlib.import_module(mod_name)
    fn = getattr(module, fn_name, None)
    if not callable(fn):
        raise ValueError(f"Callable not found: {spec}")
    return fn


def _filter_metrics(metrics: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
    if not metrics:
        return None
    out: Dict[str, int] = {}
    for k, v in metrics.items():
        if k in ALLOWED_METRIC_COLUMNS:
            out[k] = int(v)
        else:
            logger.warning("Ignoring unknown metric key: %s", k)
    return out or None


def run_import_orchestrator(
    conn: psycopg2.extensions.connection,
    *,
    supplier: str,
    file_path: str,
    as_of_date: date,
    triggered_by: str,
    import_fn: Callable[..., Dict[str, Any]],
    processing_mode: str = "atomic",
    create_skipped_audit_row: bool = True,
    envelope_extra: Optional[Dict[str, Any]] = None,
    import_kwargs: Optional[Dict[str, Any]] = None,
) -> OrchestratorResult:
    """
    import_fn contract (recommended):
      def import_fn(conn, *, supplier, file_path, as_of_date, run_id, envelope_id, **kwargs) -> dict:
          return {"metrics": {...}, "artifacts": {...}}
    """
    registry = ImportRunRegistry(conn, processing_mode=processing_mode)  # type: ignore[arg-type]

    action, _, blocker = registry.check_attempt_or_get_blocker(
        supplier=supplier,
        file_path=file_path,
        as_of_date=as_of_date,
    )

    if action in ("SKIP_ALREADY_SUCCESS", "SKIP_ALREADY_RUNNING"):
        reason = f"{action}: {blocker}"
        logger.info("import_orchestrator: skip. supplier=%s as_of_date=%s reason=%s", supplier, as_of_date, reason)

        if create_skipped_audit_row:
            try:
                registry.create_skipped_attempt(
                    supplier=supplier,
                    file_path=file_path,
                    as_of_date=as_of_date,
                    reason=reason,
                    triggered_by=triggered_by,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Failed to create skipped audit row (non-fatal).")

        return OrchestratorResult(status="skipped", reason=reason)

    # 1) create attempt (pending)
    try:
        run_id = registry.create_attempt(
            supplier=supplier,
            file_path=file_path,
            as_of_date=as_of_date,
            triggered_by=triggered_by,
            as_of_datetime=None,
            envelope_id=None,
            import_config=import_kwargs,
        )
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        # Race: someone created a blocker after our check.
        action2, _, blocker2 = registry.check_attempt_or_get_blocker(supplier=supplier, file_path=file_path, as_of_date=as_of_date)
        reason = f"IntegrityError -> {action2}: {blocker2}"
        logger.info("import_orchestrator: skip after integrity error. %s", reason)
        return OrchestratorResult(status="skipped", reason=reason)
    except Exception:
        conn.rollback()
        raise

    # 2) mark running
    registry.mark_running(run_id)
    conn.commit()

    # 3) create envelope best-effort and attach to run (separate commit)
    envelope_id: Optional[UUID] = None
    try:
        env_res = create_ingest_envelope_best_effort(
            conn,
            supplier=supplier,
            file_path=file_path,
            as_of_date=as_of_date,
            as_of_datetime=None,
            extra=envelope_extra,
        )
        if env_res.envelope_id:
            envelope_id = env_res.envelope_id
            conn.commit()
            registry.attach_envelope(run_id, envelope_id)
            conn.commit()
        else:
            conn.rollback()  # ensure clean tx after best-effort operations
            logger.warning("ingest_envelope not created: %s", env_res.reason)
    except Exception:
        conn.rollback()
        logger.exception("Envelope creation/attach failed (non-fatal). Continuing without envelope_id.")
        envelope_id = None

    # 4) import transaction (must not include registry writes)
    import_kwargs = import_kwargs or {}
    try:
        started = datetime.utcnow()
        logger.info(
            "import_run_started supplier=%s run_id=%s envelope_id=%s as_of_date=%s",
            supplier,
            run_id,
            envelope_id,
            as_of_date,
        )

        with conn:  # commits or rollbacks ONLY import work
            payload = import_fn(
                conn,
                supplier=supplier,
                file_path=file_path,
                as_of_date=as_of_date,
                run_id=run_id,
                envelope_id=envelope_id,
                **import_kwargs,
            )

        finished = datetime.utcnow()
        duration_ms = int((finished - started).total_seconds() * 1000)

        metrics = _filter_metrics(
            payload.get("metrics") if isinstance(payload, dict) else None)

        artifacts = None
        if isinstance(payload, dict):
            # accept both keys: new ("artifact_paths") and legacy ("artifacts")
            artifacts = payload.get("artifact_paths") or payload.get("artifacts")

        if artifacts is not None and not isinstance(artifacts, dict):
            logger.warning("artifact_paths/artifacts must be a dict[str,"
                           "str]; got: %s", type(artifacts))
            artifacts = None

        registry.mark_success(
            run_id,
            metrics=metrics,
            artifact_paths=artifacts,
            envelope_id=envelope_id,
        )
        conn.commit()

        logger.info(
            "import_run_success supplier=%s run_id=%s envelope_id=%s duration_ms=%s metrics=%s",
            supplier,
            run_id,
            envelope_id,
            duration_ms,
            metrics,
        )
        return OrchestratorResult(status="success", run_id=run_id, envelope_id=envelope_id)

    except Exception as exc:
        conn.rollback()
        registry.mark_failed(
            run_id,
            error_summary=str(exc),
            error_details={"type": type(exc).__name__},
        )
        conn.commit()

        logger.exception("import_run_failed supplier=%s run_id=%s envelope_id=%s", supplier, run_id, envelope_id)
        return OrchestratorResult(status="failed", run_id=run_id, envelope_id=envelope_id, reason=str(exc))
