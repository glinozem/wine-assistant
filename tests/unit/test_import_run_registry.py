import os
from datetime import date

import psycopg2
import pytest

from scripts.idempotency import compute_file_sha256
from scripts.import_run_registry import ImportRunRegistry

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _clean_import_runs(db_connection):
    # ВАЖНО: тесты делают COMMIT, поэтому чистим явно
    with db_connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE import_runs CASCADE")
    db_connection.commit()


@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "supplier1_20251223.xlsx"
    p.write_text("Sample data")
    return str(p)


def test_success_blocks_new_pending(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()

    registry.mark_running(run_id)
    db_connection.commit()

    registry.mark_success(run_id)
    db_connection.commit()

    with pytest.raises(psycopg2.IntegrityError) as exc:
        registry.create_attempt(
            supplier="supplier1",
            file_path=sample_file,
            as_of_date=date(2025, 12, 23),
            triggered_by="test2",
        )
        db_connection.commit()

    assert "ux_import_runs_blocking_key" in str(exc.value)
    db_connection.rollback()  # critical: recover connection


def test_failed_allows_retry(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()

    registry.mark_running(run_id)
    db_connection.commit()

    registry.mark_failed(run_id, "Test error")
    db_connection.commit()

    run_id2 = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="retry",
    )
    db_connection.commit()

    assert run_id2 != run_id


def test_blocker_first_with_anomaly(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    run_id1 = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test1",
    )
    db_connection.commit()
    registry.mark_running(run_id1)
    db_connection.commit()
    registry.mark_success(run_id1)
    db_connection.commit()

    sha = compute_file_sha256(sample_file)
    with db_connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO import_runs (
                supplier, source_filename, file_sha256, as_of_date,
                status, error_summary, triggered_by
            )
            VALUES (%s,%s,%s,%s,'failed','Anomaly','direct_sql')
            """,
            ("supplier1", os.path.basename(sample_file), sha, date(2025, 12, 23)),
        )
    db_connection.commit()

    action, _, blocker = registry.check_attempt_or_get_blocker(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
    )
    assert action == "SKIP_ALREADY_SUCCESS"
    assert str(blocker["run_id"]) == str(run_id1)


def test_running_blocks_concurrent(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()
    registry.mark_running(run_id)
    db_connection.commit()

    action, _, blocker = registry.check_attempt_or_get_blocker(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
    )
    assert action == "SKIP_ALREADY_RUNNING"
    assert str(blocker["run_id"]) == str(run_id)


def test_skipped_does_not_block(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    skip_id = registry.create_skipped_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        reason="Test skip",
        triggered_by="test",
    )
    db_connection.commit()

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test2",
    )
    db_connection.commit()

    assert run_id != skip_id


def test_registry_survives_import_rollback(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()

    registry.mark_running(run_id)
    db_connection.commit()

    try:
        with db_connection:
            with db_connection.cursor() as cur:
                cur.execute("SELECT 1")
            raise RuntimeError("Simulated import failure")
    except RuntimeError:
        pass

    registry.mark_failed(run_id, "Import failed")
    db_connection.commit()

    status = registry.get_run_status(run_id)
    assert status["status"] == "failed"
    assert status["error_summary"] == "Import failed"


def test_v_import_staleness_has_success_and_last_error_coalesce(db_connection, sample_file):
    registry = ImportRunRegistry(db_connection)

    sha = compute_file_sha256(sample_file)
    with db_connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO import_runs (
                supplier, source_filename, file_sha256, as_of_date,
                status, error_summary, triggered_by,
                started_at, finished_at
            )
            VALUES (%s,%s,%s,%s,'failed','Failed-without-finished','direct_sql', NOW(), NULL)
            """,
            ("supplier1", os.path.basename(sample_file), sha, date(2025, 12, 23)),
        )
    db_connection.commit()

    st = registry.get_staleness("supplier1")
    assert st is not None
    assert st["has_success"] is False
    assert st["last_error"] == "Failed-without-finished"

    run_id = registry.create_attempt(
        supplier="supplier1",
        file_path=sample_file,
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()
    registry.mark_running(run_id)
    db_connection.commit()
    registry.mark_success(run_id)
    db_connection.commit()

    st2 = registry.get_staleness("supplier1")
    assert st2 is not None
    assert st2["has_success"] is True
    assert st2["last_success_at"] is not None
