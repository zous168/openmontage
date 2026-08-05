"""CR-168 · moments 模块开关读写."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.module_enabled import read_module_enabled, set_module_enabled


@pytest.fixture
def moments_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "wechat"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    ConfigManager.reset()
    ensure_config_runtime()


def test_moments_default_disabled_when_missing(moments_env: None) -> None:
    assert read_module_enabled("wechat", "moments") is False


def test_moments_read_write(moments_env: None) -> None:
    set_module_enabled("wechat", "moments", True)
    assert read_module_enabled("wechat", "moments") is True
    set_module_enabled("wechat", "moments", False)
    assert read_module_enabled("wechat", "moments") is False
