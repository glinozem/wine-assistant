import io
import os
import sys
from pathlib import Path

import pytest
from flask import Flask, jsonify, request
from werkzeug.datastructures import MultiDict


@pytest.fixture()
def ops_client(tmp_path, monkeypatch):
    """
    Изолированный Flask app + ops endpoints с замонкейпатченными директориями.

    ВАЖНО: monkeypatch делаем на уровне модуля api.ops_daily_import:
      - INBOX_DIR, ARCHIVE_DIR, QUARANTINE_DIR, LOGS_DIR
    чтобы тесты НЕ трогали реальные data/* директории проекта.
    """
    from api import ops_daily_import as mod

    inbox = tmp_path / "inbox"
    archive = tmp_path / "archive"
    quarantine = tmp_path / "quarantine"
    logs = tmp_path / "logs"

    inbox.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "INBOX_DIR", inbox)
    monkeypatch.setattr(mod, "ARCHIVE_DIR", archive)
    monkeypatch.setattr(mod, "QUARANTINE_DIR", quarantine)
    monkeypatch.setattr(mod, "LOGS_DIR", logs)

    app = Flask(__name__)

    # минимальный API-key gate (как требует Issue: endpoints защищены X-API-Key)
    def require_api_key(fn):
        def wrapper(*a, **kw):
            if request.headers.get("X-API-Key") != "testkey":
                return jsonify({"error": "forbidden"}), 403
            return fn(*a, **kw)

        wrapper.__name__ = fn.__name__
        return wrapper

    # db_* для этих тестов не нужны; дадим “заглушки”
    def db_connect():
        return None, "db disabled for unit tests"

    def db_query(conn, sql, params=()):
        return []

    mod.register_ops_daily_import(app, require_api_key, db_connect, db_query)
    return app.test_client(), mod, {"inbox": inbox, "archive": archive, "quarantine": quarantine, "logs": logs}


# ──────────────────────────────────────────────────────────────────────────────
# Upload tests
# ──────────────────────────────────────────────────────────────────────────────

def test_upload_happy_path_saves_file_and_returns_saved_name(ops_client):
    client, _mod, dirs = ops_client

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"dummy-xlsx-bytes"), "prices.xlsx")},
        content_type="multipart/form-data",
    )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None

    assert data["uploaded"] and len(data["uploaded"]) == 1
    assert data["uploaded"][0]["original_name"] == "prices.xlsx"
    assert data["uploaded"][0]["saved_name"] == "prices.xlsx"
    assert data["uploaded"][0]["status"] == "UPLOADED"

    saved = dirs["inbox"] / "prices.xlsx"
    assert saved.exists()
    assert saved.read_bytes() == b"dummy-xlsx-bytes"

    # в ответе также отдаётся обновлённый список inbox
    inbox_files = data.get("inbox", {}).get("files", [])
    assert any(f.get("name") == "prices.xlsx" for f in inbox_files)


def test_upload_name_conflict_allocates_prices_1(ops_client):
    client, _mod, dirs = ops_client

    r1 = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"v1"), "prices.xlsx")},
        content_type="multipart/form-data",
    )
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1 and d1["uploaded"] and d1["uploaded"][0]["saved_name"] == "prices.xlsx"

    r2 = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"v2"), "prices.xlsx")},
        content_type="multipart/form-data",
    )
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2 and d2["uploaded"] and len(d2["uploaded"]) == 1

    assert d2["uploaded"][0]["saved_name"] == "prices (1).xlsx"
    assert (dirs["inbox"] / "prices.xlsx").read_bytes() == b"v1"
    assert (dirs["inbox"] / "prices (1).xlsx").read_bytes() == b"v2"

def test_upload_accepts_files_array_field_name_files_brackets(ops_client):
    client, _mod, dirs = ops_client

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files[]": (io.BytesIO(b"x"), "a.xlsx")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data and data["uploaded"] and data["uploaded"][0]["saved_name"] == "a.xlsx"
    assert (dirs["inbox"] / "a.xlsx").exists()


def test_upload_rejects_non_xlsx_extension(ops_client):
    client, _mod, dirs = ops_client

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"not-xlsx"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None

    assert data["uploaded"] == []
    assert data["rejected"] and len(data["rejected"]) == 1
    rej = data["rejected"][0]
    assert rej["original_name"] == "notes.txt"
    assert rej["reason"] == "INVALID_FILE"
    assert "xlsx" in rej["message"].lower()

    assert not (dirs["inbox"] / "notes.txt").exists()


@pytest.mark.parametrize(
    "bad_name",
    [
        "../evil.xlsx",
        "a/b.xlsx",
        r"a\b.xlsx",
        "-arg.xlsx",
        "...\x00.xlsx",
    ],
)
def test_upload_rejects_dangerous_filenames(ops_client, bad_name):
    client, _mod, dirs = ops_client

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"x"), bad_name)},
        content_type="multipart/form-data",
    )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None

    assert data["uploaded"] == []
    assert data["rejected"] and len(data["rejected"]) == 1
    assert data["rejected"][0]["reason"] == "INVALID_FILE"


def test_upload_too_many_files_returns_400(ops_client):
    client, mod, _dirs = ops_client

    # MAX_FILES + 1
    data = MultiDict()
    for i in range(mod.MAX_FILES + 1):
        data.add("files", (io.BytesIO(b"x"), f"f{i}.xlsx"))

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data=data,
        content_type="multipart/form-data",
    )

    assert r.status_code == 400
    payload = r.get_json()
    assert payload and "Too many files" in payload.get("error", "")


def test_upload_rejects_file_too_large(ops_client, monkeypatch):
    client, mod, dirs = ops_client

    # делаем лимит очень маленьким, чтобы не грузить мегабайты
    monkeypatch.setattr(mod, "MAX_UPLOAD_FILE_BYTES", 10)
    # MAX_UPLOAD_FILE_MB используется только для текста сообщения — можно не проверять

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"0123456789A"), "big.xlsx")},  # 11 bytes
        content_type="multipart/form-data",
    )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None

    assert data["uploaded"] == []
    assert data["rejected"] and data["rejected"][0]["reason"] == "FILE_TOO_LARGE"
    assert not (dirs["inbox"] / "big.xlsx").exists()


def test_upload_total_payload_too_large_returns_413(ops_client, monkeypatch):
    client, mod, _dirs = ops_client

    # гарантированно триггерим content_length pre-check
    monkeypatch.setattr(mod, "MAX_UPLOAD_TOTAL_BYTES", 1)

    r = client.post(
        "/api/v1/ops/daily-import/inbox/upload",
        headers={"X-API-Key": "testkey"},
        data={"files": (io.BytesIO(b"0123456789"), "x.xlsx")},
        content_type="multipart/form-data",
    )

    assert r.status_code == 413
    data = r.get_json()
    assert data and data.get("error") == "payload_too_large"


# ──────────────────────────────────────────────────────────────────────────────
# Download tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["archive", "quarantine", "logs"])
def test_download_happy_path(kind, ops_client):
    client, _mod, dirs = ops_client

    base: Path = dirs[kind]
    (base / "hello.txt").write_bytes(b"hello-world")

    r = client.get(
        f"/api/v1/ops/files/{kind}/hello.txt",
        headers={"X-API-Key": "testkey"},
    )

    assert r.status_code == 200
    assert r.data == b"hello-world"
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower()


def test_download_invalid_kind_returns_400(ops_client):
    client, _mod, _dirs = ops_client

    r = client.get(
        "/api/v1/ops/files/nope/x.txt",
        headers={"X-API-Key": "testkey"},
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data and data.get("error") == "Invalid kind"


def test_download_path_traversal_blocked_403(ops_client):
    client, _mod, dirs = ops_client

    # создаём “секрет” вне archive
    secret = dirs["archive"].parent / "secret.txt"
    secret.write_bytes(b"top-secret")

    r = client.get(
        "/api/v1/ops/files/archive/../secret.txt",
        headers={"X-API-Key": "testkey"},
    )

    assert r.status_code == 403
    data = r.get_json()
    assert data and "Path traversal" in data.get("error", "")


def test_download_not_found_returns_404(ops_client):
    client, _mod, _dirs = ops_client

    r = client.get(
        "/api/v1/ops/files/archive/missing.txt",
        headers={"X-API-Key": "testkey"},
    )
    assert r.status_code == 404
    data = r.get_json()
    assert data and data.get("error") == "File not found"


def test_ops_endpoints_require_api_key(ops_client):
    client, _mod, _dirs = ops_client

    r1 = client.get("/api/v1/ops/daily-import/inbox")
    r2 = client.get("/api/v1/ops/files/archive/anything.txt")
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_download_logs_allows_nested_paths_when_inside_base(ops_client):
    client, _mod, dirs = ops_client

    nested_dir = dirs["logs"] / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "x.txt").write_bytes(b"x")

    r = client.get(
        "/api/v1/ops/files/logs/nested/x.txt",
        headers={"X-API-Key": "testkey"},
    )

    assert r.status_code == 200
    assert r.data == b"x"
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower()


def test_download_logs_blocks_traversal_percent_encoded(ops_client):
    client, _mod, dirs = ops_client

    # файл вне logs
    secret = dirs["logs"].parent / "secret.txt"
    secret.write_bytes(b"top-secret")

    # %2e%2e == '..'
    r = client.get(
        "/api/v1/ops/files/logs/%2e%2e/secret.txt",
        headers={"X-API-Key": "testkey"},
    )

    assert r.status_code == 403
    data = r.get_json()
    assert data and data.get("error") == "Path traversal blocked"


def test_download_logs_blocks_absolute_path(ops_client):
    client, _mod, dirs = ops_client

    # На Windows abs path вида C:\...
    if os.name == "nt":
        relpath = "C:\\Windows\\System32\\drivers\\etc\\hosts"
    else:
        relpath = "/etc/passwd"

    # На Linux leading "/" создаёт URL с двойным слэшем (.../logs//etc/passwd),
    # Werkzeug может ответить 308 redirect ещё до попадания в handler.
    # В любом случае system file не должен быть отдан.
    r = client.get(
        f"/api/v1/ops/files/logs/{relpath}",
        headers={"X-API-Key": "testkey"},
        follow_redirects=True,
    )

    assert r.status_code in (403, 404)
    if r.status_code == 403:
        data = r.get_json()
        assert data and data.get("error") == "Path traversal blocked"
