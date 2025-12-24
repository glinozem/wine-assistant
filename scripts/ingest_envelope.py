from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from scripts.idempotency import compute_file_sha256

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnvelopeCreateResult:
    envelope_id: Optional[UUID]
    reason: Optional[str] = None


def _table_exists(conn: psycopg2.extensions.connection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (table,))
        return cur.fetchone()[0] is not None


def _get_columns(conn: psycopg2.extensions.connection, table_name: str) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT column_name, is_nullable, column_default, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return [dict(r) for r in cur.fetchall()]


def create_ingest_envelope_best_effort(
    conn: psycopg2.extensions.connection,
    *,
    supplier: str,
    file_path: str,
    as_of_date: date,
    as_of_datetime: Optional[datetime] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> EnvelopeCreateResult:
    """
    Best-effort envelope creation.
    Strategy:
      1) If ingest_envelope doesn't exist => return None.
      2) Try INSERT DEFAULT VALUES RETURNING envelope_id.
      3) Else, insert using a minimal set of known columns if present.
      4) If schema requires additional NOT NULL columns w/o defaults => return None with reason.
    """
    if not _table_exists(conn, "public.ingest_envelope"):
        return EnvelopeCreateResult(None, "ingest_envelope table not found")

    cols = _get_columns(conn, "ingest_envelope")
    colset = {c["column_name"] for c in cols}

    # 1) simplest possible (works if table has defaults)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ingest_envelope DEFAULT VALUES RETURNING envelope_id")
            envelope_id = cur.fetchone()[0]
        logger.info("Created ingest_envelope via DEFAULT VALUES: %s", envelope_id)
        return EnvelopeCreateResult(envelope_id, None)
    except Exception as exc:
        conn.rollback()  # ensure connection is usable for next attempts
        logger.debug("DEFAULT VALUES insert failed, fallback to column-aware insert: %s", exc)

    # 2) column-aware insert (only if schema allows)
    file_sha256 = compute_file_sha256(file_path)
    file_size = os.path.getsize(file_path)
    source_filename = os.path.basename(file_path)

    envelope_id = uuid4()

    candidate_values: dict[str, Any] = {}
    if "envelope_id" in colset:
        candidate_values["envelope_id"] = envelope_id
    if "supplier" in colset:
        candidate_values["supplier"] = supplier
    if "source_filename" in colset:
        candidate_values["source_filename"] = source_filename
    if "file_sha256" in colset:
        candidate_values["file_sha256"] = file_sha256
    if "file_size_bytes" in colset:
        candidate_values["file_size_bytes"] = file_size
    if "as_of_date" in colset:
        candidate_values["as_of_date"] = as_of_date
    if "as_of_datetime" in colset:
        candidate_values["as_of_datetime"] = as_of_datetime
    if "created_at" in colset:
        candidate_values["created_at"] = datetime.utcnow()
    if "updated_at" in colset:
        candidate_values["updated_at"] = datetime.utcnow()
    if "metadata" in colset:
        candidate_values["metadata"] = extra

    required_missing: list[str] = []
    for c in cols:
        name = c["column_name"]
        if c["is_nullable"] == "NO" and c["column_default"] is None:
            if name not in candidate_values:
                required_missing.append(name)

    if required_missing:
        return EnvelopeCreateResult(
            None,
            f"ingest_envelope schema requires NOT NULL columns without defaults: {required_missing}",
        )

    if not candidate_values:
        return EnvelopeCreateResult(None, "no compatible columns found to insert envelope")

    columns_sql = ", ".join(candidate_values.keys())
    placeholders = ", ".join(["%s"] * len(candidate_values))
    params = list(candidate_values.values())

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO ingest_envelope ({columns_sql}) VALUES ({placeholders}) RETURNING envelope_id",
                params,
            )
            created_id = cur.fetchone()[0]
        logger.info("Created ingest_envelope (column-aware): %s", created_id)
        return EnvelopeCreateResult(created_id, None)
    except Exception as exc:
        conn.rollback()
        return EnvelopeCreateResult(None, f"envelope insert failed: {exc}")
