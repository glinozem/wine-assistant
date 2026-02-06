import api.app as app_mod


def _reset_image_cache() -> None:
    app_mod._IMAGE_INDEX = None
    app_mod._IMAGE_INDEX_MTIME_NS = None
    app_mod._IMAGE_INDEX_TS = None


def test_image_index_rebuilds_on_dir_mtime_change(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    (images_dir / "D100.jpg").write_bytes(b"jpg")
    monkeypatch.setenv("WINE_IMAGE_DIR", str(images_dir))
    monkeypatch.setattr(app_mod, "_IMAGE_INDEX_TTL_SECONDS", 0)

    mtime = {"v": 1}

    def fake_mtime(_: object) -> int:
        return int(mtime["v"])

    monkeypatch.setattr(app_mod, "_image_dir_mtime_ns", fake_mtime)
    _reset_image_cache()

    assert app_mod._get_best_image_filename("D100") == "D100.jpg"

    (images_dir / "D200.png").write_bytes(b"png")
    mtime["v"] = 2

    assert app_mod._get_best_image_filename("D200") == "D200.png"


def test_image_index_rebuilds_by_ttl_when_mtime_is_stable(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    (images_dir / "D300.jpg").write_bytes(b"jpg")
    monkeypatch.setenv("WINE_IMAGE_DIR", str(images_dir))

    monkeypatch.setattr(app_mod, "_image_dir_mtime_ns", lambda _: 123)
    monkeypatch.setattr(app_mod, "_IMAGE_INDEX_TTL_SECONDS", 1)

    t = {"now": 1000.0}
    monkeypatch.setattr(app_mod.time, "time", lambda: t["now"])
    _reset_image_cache()

    assert app_mod._get_best_image_filename("D300") == "D300.jpg"

    (images_dir / "D400.png").write_bytes(b"png")
    t["now"] = 1000.5
    assert app_mod._get_best_image_filename("D400") is None

    t["now"] = 1002.0
    assert app_mod._get_best_image_filename("D400") == "D400.png"


def test_image_index_handles_missing_dir(tmp_path, monkeypatch):
    missing_dir = tmp_path / "missing"
    monkeypatch.setenv("WINE_IMAGE_DIR", str(missing_dir))
    monkeypatch.setattr(app_mod, "_IMAGE_INDEX_TTL_SECONDS", 0)
    _reset_image_cache()

    assert app_mod._get_best_image_filename("D999") is None
