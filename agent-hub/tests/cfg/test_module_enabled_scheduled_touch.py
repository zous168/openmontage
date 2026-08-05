"""P1-2 · scheduled_touch 模块开关兼容根级 enabled."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.module_enabled import read_module_enabled


@pytest.fixture
def touch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_scheduled_touch_reads_root_enabled_key(touch_env: None) -> None:
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {"scheduled_touch": {"enabled": False}},
    )
    assert read_module_enabled("wechat", "scheduled_touch") is False


def test_scheduled_touch_prefers_scheduler_enabled_over_legacy(touch_env: None) -> None:
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {
            "scheduler": {"scheduled_touch": {"enabled": False, "time": "09:00"}},
            "scheduled_touch": {"enabled": True, "time": "09:00"},
        },
    )
    assert read_module_enabled("wechat", "scheduled_touch") is False
