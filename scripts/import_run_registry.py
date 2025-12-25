"""
Import Run Registry (v1.0 PRODUCTION)
====================================

Purpose:
- Journal of import attempts (import_runs) with retry support.
- Extends ingest_envelope (optional envelope_id link).
- Reuses scripts.idempotency.compute_file_sha256() (no duplication).

CRITICAL: Transaction Separation Contract (R0.2)
-----------------------------------------------
Registry writes MUST be committed separately from the import data transaction.

Typical pattern:
1) action = check_attempt_or_get_blocker()  # read-only
2) run_id = create_attempt(); conn.commit()
3) mark_running(run_id); conn.commit()
4) run import transaction (with conn/cur); commit/rollback
5) mark_success/mark_failed; conn.commit()

IntegrityError handling:
- After psycopg2.IntegrityError, connection is aborted.
  Caller MUST call conn.rollback() before any further operations.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Literal, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from scripts.idempotency import compute_file_sha256

logger = logging.getLogger(__name__)

ImportStatus = Literal["pending", "running", "success", "failed", "skipped", "rolled_back"]
ProcessingMode = Literal["atomic", "chunked"]
AttemptAction = Literal["START", "SKIP_ALREADY_SUCCESS", "SKIP_ALREADY_RUNNING", "RETRY_AFTER_FAILED"]


@dataclass(frozen=True)
class Blocker:
    run_id: UUID
    status: ImportStatus
    error_summary: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]


class ImportRunRegistry:
    def __init__(self, connection: psycopg2.extensions.connection, processing_mode: ProcessingMode = "atomic"):
        self.conn = connection
        self.processing_mode = processing_mode

    def check_attempt_or_get_blocker(
        self,
        supplier: str,
        file_path: str,
        as_of_date: date,
    ) -> Tuple[AttemptAction, Optional[UUID], Optional[Dict[str, Any]]]:
        """
        Priority:
        1) blocker: success/pending/running
        2) failed/rolled_back => retry allowed
        3) none => START
        """
        file_sha256 = compute_file_sha256(file_path)

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1) blocker first
            cur.execute(
                """
                SELECT run_id, status, error_summary, created_at, started_at, envelope_id
                FROM import_runs
                WHERE supplier = %s
                  AND file_sha256 = %s
                  AND as_of_date = %s
                  AND status IN ('success','pending','running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (supplier, file_sha256, as_of_date),
            )
            blocker = cur.fetchone()
            if blocker:
                if blocker["status"] == "success":
                    return "SKIP_ALREADY_SUCCESS", None, dict(blocker)
                return "SKIP_ALREADY_RUNNING", None, dict(blocker)

            # 2) last failed/rolled_back
            cur.execute(
                """
                SELECT run_id, status, error_summary, created_at, started_at
                FROM import_runs
                WHERE supplier = %s
                  AND file_sha256 = %s
                  AND as_of_date = %s
                  AND status IN ('failed','rolled_back')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (supplier, file_sha256, as_of_date),
            )
            failed = cur.fetchone()
            if failed:
                return "RETRY_AFTER_FAILED", None, dict(failed)

            return "START", None, None

    def create_attempt(
        self,
        supplier: str,
        file_path: str,
        as_of_date: date,
        triggered_by: str,
        as_of_datetime: Optional[datetime] = None,
        envelope_id: Optional[UUID] = None,
        import_config: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Creates a new 'pending' attempt.
        NOTE: caller must commit.
        Raises psycopg2.IntegrityError if blocking attempt exists.
        """
        file_sha256 = compute_file_sha256(file_path)
        file_size = os.path.getsize(file_path)
        source_filename = os.path.basename(file_path)
        envelope_id_param = str(
            envelope_id) if envelope_id is not None else None

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO import_runs (
                    supplier, source_filename, file_sha256, file_size_bytes,
                    envelope_id,
                    as_of_date, as_of_datetime,
                    status,
                    triggered_by, processing_mode,
                    import_config
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s)
                RETURNING run_id
                """,
                (
                    supplier,
                    source_filename,
                    file_sha256,
                    file_size,
                    envelope_id_param,
                    as_of_date,
                    as_of_datetime,
                    triggered_by,
                    self.processing_mode,
                    Json(import_config) if import_config else None,
                ),
            )
            run_id = cur.fetchone()[0]
            logger.info("Created import attempt %s for %s/%s", run_id, supplier, source_filename)
            return run_id

    def create_skipped_attempt(
        self,
        supplier: str,
        file_path: str,
        as_of_date: date,
        reason: str,
        triggered_by: str,
        envelope_id: Optional[UUID] = None,
    ) -> UUID:
        """
        Creates an audit row with status='skipped' (does not block future attempts).
        NOTE: caller must commit.
        """
        file_sha256 = compute_file_sha256(file_path)
        source_filename = os.path.basename(file_path)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO import_runs (
                    supplier, source_filename, file_sha256,
                    envelope_id,
                    as_of_date,
                    status,
                    error_summary,
                    triggered_by,
                    finished_at
                )
                VALUES (%s,%s,%s,%s,%s,'skipped',%s,%s,NOW())
                RETURNING run_id
                """,
                (supplier, source_filename, file_sha256, envelope_id, as_of_date, reason, triggered_by),
            )
            run_id = cur.fetchone()[0]
            logger.info("Created skipped attempt %s (%s)", run_id, reason)
            return run_id

    def mark_running(self, run_id: UUID) -> None:
        """NOTE: caller must commit."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_runs
                SET status = 'running',
                    started_at = NOW()
                WHERE run_id = %s
                  AND status = 'pending'
                """,
                (str(run_id),),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Cannot mark running: {run_id} (expected status 'pending')")
            logger.info("Marked run %s as running", run_id)

    def attach_envelope(self, run_id: UUID, envelope_id: UUID) -> None:
        """
        Attach envelope_id to an existing run.
        NOTE: caller must commit.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_runs
                SET envelope_id = %s
                WHERE run_id = %s
                  AND status IN ('pending','running')
                """,
                (str(envelope_id), str(run_id)),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Cannot attach envelope: {run_id} (expected status pending/running)")
            logger.info("Attached envelope %s to run %s", envelope_id, run_id)

    def mark_success(
        self,
        run_id: UUID,
        metrics: Optional[Dict[str, int]] = None,
        artifact_paths: Optional[Dict[str, str]] = None,
        envelope_id: Optional[UUID] = None,
    ) -> None:
        """NOTE: caller must commit."""
        set_parts = ["status = 'success'", "finished_at = NOW()"]
        params: list[Any] = []

        if metrics:
            for k, v in metrics.items():
                set_parts.append(f"{k} = %s")
                params.append(v)

        if artifact_paths:
            set_parts.append("artifact_paths = %s")
            params.append(Json(artifact_paths))

        if envelope_id:
            set_parts.append("envelope_id = %s")
            params.append(str(envelope_id))

        params.append(str(run_id))

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE import_runs
                SET {", ".join(set_parts)}
                WHERE run_id = %s
                  AND status = 'running'
                """,
                params,
            )
            if cur.rowcount == 0:
                raise ValueError(f"Cannot mark success: {run_id} (expected status 'running')")
            logger.info("Marked run %s as success", run_id)

    def mark_failed(
        self,
        run_id: UUID,
        error_summary: str,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """NOTE: caller must commit."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_runs
                SET status = 'failed',
                    finished_at = NOW(),
                    error_summary = %s,
                    error_details = %s
                WHERE run_id = %s
                  AND status = 'running'
                """,
                (error_summary, Json(error_details) if error_details else
                None, str(run_id)),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Cannot mark failed: {run_id} (expected status 'running')")
            logger.info("Marked run %s as failed: %s", run_id, error_summary)

    def get_run_status(self, run_id: UUID) -> Dict[str, Any]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *,
                       EXTRACT(EPOCH FROM (finished_at - started_at))::NUMERIC(10,2) AS duration_seconds
                FROM import_runs
                WHERE run_id = %s
                """,
                (str(run_id),),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Run not found: {run_id}")
            return dict(row)

    def get_staleness(self, supplier: str) -> Optional[Dict[str, Any]]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM v_import_staleness
                WHERE supplier = %s
                """,
                (supplier,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_recent(
        self,
        limit: int = 20,
        supplier: Optional[str] = None,
        status: Optional[ImportStatus] = None,
    ) -> list[Dict[str, Any]]:
        where_parts = []
        params: list[Any] = []

        if supplier:
            where_parts.append("supplier = %s")
            params.append(supplier)
        if status:
            where_parts.append("status = %s")
            params.append(status)

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params.append(limit)

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM v_import_runs_summary
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
