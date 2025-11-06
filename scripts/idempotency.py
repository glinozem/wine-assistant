"""
Idempotency module for ETL processes.

Implements file fingerprinting using SHA256 to prevent duplicate imports.
Issue: #80
"""

import hashlib
import logging
from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import UUID

import psycopg2

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        64-character hex string (SHA256 hash)

    Example:
        >>> compute_file_sha256("data.xlsx")
        'a3f4d9e2b8c1...'  # 64 hex chars
    """
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        # Read file in chunks to handle large files
        while True:
            chunk = f.read(8192)  # 8KB chunks
            if not chunk:
                break
            sha256.update(chunk)

    file_hash = sha256.hexdigest()
    logger.debug(f"Computed SHA256 for {file_path}: {file_hash[:16]}...")
    return file_hash


def check_file_exists(
    conn: psycopg2.extensions.connection, file_hash: str
) -> Optional[Dict[str, Any]]:
    """
    Check if a file with given SHA256 hash already exists in the database.

    Args:
        conn: Database connection
        file_hash: SHA256 hash of the file (64 hex chars)

    Returns:
        Dict with envelope info if exists, None otherwise

    Example:
        >>> existing = check_file_exists(conn, "a3f4d9e2...")
        >>> if existing:
        ...     print(f"File already imported: {existing['envelope_id']}")
    """
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
                   SELECT envelope_id,
                          file_name,
                          file_sha256,
                          upload_timestamp,
                          status,
                          rows_inserted,
                          rows_updated,
                          rows_failed
                   FROM ingest_envelope
                   WHERE file_sha256 = %s
                   """,
        (file_hash,),
    )

    result = cursor.fetchone()
    cursor.close()

    if result:
        logger.info(
            f"File already exists in database",
            extra={
                "envelope_id": str(result["envelope_id"]),
                "file_name": result["file_name"],
                "status": result["status"],
                "upload_timestamp": result["upload_timestamp"].isoformat(),
            },
        )

    return dict(result) if result else None


def create_envelope(
    conn: psycopg2.extensions.connection,
    file_name: str,
    file_hash: str,
    file_path: Optional[str] = None,
    file_size_bytes: Optional[int] = None,
) -> UUID:
    """
    Create a new ingest envelope in the database.

    Args:
        conn: Database connection
        file_name: Name of the file (e.g., "Price_2025_01_20.xlsx")
        file_hash: SHA256 hash of the file
        file_path: Full path to the file (optional)
        file_size_bytes: File size in bytes (optional)

    Returns:
        UUID of the created envelope

    Example:
        >>> envelope_id = create_envelope(conn, "data.xlsx", "a3f4d9e2...")
        >>> print(f"Created envelope: {envelope_id}")
    """
    cursor = conn.cursor()

    cursor.execute(
        """
                   INSERT INTO ingest_envelope (file_name,
                                                file_sha256,
                                                file_path,
                                                file_size_bytes,
                                                status)
                   VALUES (%s, %s, %s, %s, 'processing') RETURNING envelope_id
                   """,
        (file_name, file_hash, file_path, file_size_bytes),
    )

    envelope_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()

    logger.info(
        f"Created new envelope",
        extra={
            "envelope_id": str(envelope_id),
            "file_name": file_name,
            "file_hash": file_hash[:16] + "...",
        },
    )

    return envelope_id


def update_envelope_status(
    conn: psycopg2.extensions.connection,
    envelope_id: UUID,
    status: str,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_failed: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """
    Update the status of an envelope after processing.

    Args:
        conn: Database connection
        envelope_id: UUID of the envelope
        status: 'success' or 'failed'
        rows_inserted: Number of rows inserted
        rows_updated: Number of rows updated
        rows_failed: Number of rows that failed
        error_message: Error message if status is 'failed'

    Example:
        >>> update_envelope_status(conn, envelope_id, 'success', rows_inserted=100)
    """
    cursor = conn.cursor()

    cursor.execute(
        """
                   UPDATE ingest_envelope
                   SET status                  = %s,
                       processing_completed_at = now(),
                       rows_inserted           = %s,
                       rows_updated            = %s,
                       rows_failed             = %s,
                       error_message           = %s
                   WHERE envelope_id = %s
                   """,
        (status, rows_inserted, rows_updated, rows_failed, error_message, envelope_id),
    )

    conn.commit()
    cursor.close()

    logger.info(
        f"Updated envelope status",
        extra={
            "envelope_id": str(envelope_id),
            "status": status,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "rows_failed": rows_failed,
        },
    )


def create_price_list_entry(
    conn: psycopg2.extensions.connection,
    envelope_id: UUID,
    effective_date: date,
    file_path: Optional[str] = None,
    discount_percent: Optional[float] = None,
) -> UUID:
    """
    Create a price_list entry linking the envelope to an effective date.

    Args:
        conn: Database connection
        envelope_id: UUID of the envelope
        effective_date: Date when the prices become effective
        file_path: Path to the file (optional)
        discount_percent: Discount percentage from the file (optional)

    Returns:
        UUID of the created price_list entry

    Example:
        >>> price_list_id = create_price_list_entry(
        ...     conn, envelope_id, date(2025, 1, 20), discount_percent=10.0
        ... )
    """
    cursor = conn.cursor()

    cursor.execute(
        """
                   INSERT INTO price_list (envelope_id,
                                           effective_date,
                                           file_path,
                                           discount_percent)
                   VALUES (%s, %s, %s, %s) RETURNING price_list_id
                   """,
        (envelope_id, effective_date, file_path, discount_percent),
    )

    price_list_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()

    logger.info(
        f"Created price_list entry",
        extra={
            "price_list_id": str(price_list_id),
            "envelope_id": str(envelope_id),
            "effective_date": effective_date.isoformat(),
            "discount_percent": discount_percent,
        },
    )

    return price_list_id
