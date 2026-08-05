"""本机登录凭证区 device/login_prefs.json."""

from __future__ import annotations

from core.platform.device.login_prefs import (
    clear_login_prefs,
    load_login_prefs,
    save_login_prefs,
)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: tmp_path)
    clear_login_prefs()
    empty = load_login_prefs()
    assert empty.login_name == ""
    assert empty.remember_password is False

    saved = save_login_prefs(
        login_name="aw_09cc0c9e511803f6c128ab09",
        password="admin123",
        remember_password=True,
        auto_login=True,
    )
    assert saved.login_name == "aw_09cc0c9e511803f6c128ab09"
    assert saved.password == "admin123"
    assert saved.auto_login is True

    loaded = load_login_prefs()
    assert loaded.to_api() == {
        "login_name": "aw_09cc0c9e511803f6c128ab09",
        "password": "admin123",
        "remember_password": True,
        "auto_login": True,
    }
    assert (tmp_path / "device" / "login_prefs.json").is_file()


def test_remember_off_clears_password(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: tmp_path)
    save_login_prefs(
        login_name="aw1",
        password="secret",
        remember_password=True,
        auto_login=True,
    )
    saved = save_login_prefs(
        login_name="aw1",
        password="secret",
        remember_password=False,
        auto_login=True,
    )
    assert saved.login_name == "aw1"
    assert saved.password == ""
    assert saved.remember_password is False
    assert saved.auto_login is False
