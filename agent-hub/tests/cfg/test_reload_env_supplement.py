"""``.data/.env`` is a supplement layer: reload_env must not wipe entry-injected vars."""

from __future__ import annotations

import pytest

from hermes_cli.config import invalidate_env_cache, reload_env


def test_reload_env_does_not_delete_entry_injected_known_keys(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """入口（如 .env.dev）注入的 known key，不应因 .data/.env 缺席而被删。"""
    root = tmp_path / "hub"
    root.mkdir()
    # 补充层只有渠道密钥；不含 API_SERVER_*
    (root / ".env").write_text(
        "MOARK_API_KEY=sk-from-data-env\n",
        encoding="utf-8",
    )

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    # 模拟启动脚本从 .env.dev 灌入的基线
    monkeypatch.setenv(
        "API_SERVER_KEY",
        "a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00",
    )
    monkeypatch.setenv("API_SERVER_PORT", "18789")
    monkeypatch.setenv("API_SERVER_HOST", "127.0.0.1")

    import os

    invalidate_env_cache()
    n = reload_env()

    assert n >= 1  # MOARK_API_KEY 从补充层合并
    assert os.environ["API_SERVER_KEY"].startswith("a1b2c3d4")
    assert os.environ["API_SERVER_PORT"] == "18789"
    assert os.environ["API_SERVER_HOST"] == "127.0.0.1"
    assert os.environ["MOARK_API_KEY"] == "sk-from-data-env"


def test_reload_env_overrides_when_key_present_in_data_env(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """补充层显式写出的键可以覆盖进程中的旧值。"""
    root = tmp_path / "hub"
    root.mkdir()
    (root / ".env").write_text("MOARK_API_KEY=sk-new\n", encoding="utf-8")

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    monkeypatch.setenv("MOARK_API_KEY", "sk-old")

    invalidate_env_cache()
    reload_env()

    import os

    assert os.environ["MOARK_API_KEY"] == "sk-new"
