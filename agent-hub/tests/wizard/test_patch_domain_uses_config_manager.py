"""_patch_domain 须走 ConfigManager，不应在正常 bootstrap 后 yaml-only fallback."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.registry import ConfigRegistry


@pytest.fixture
def hub_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    (profiles / "main").mkdir()
    (profiles / "main" / "config.yaml").write_text("model: test\n", encoding="utf-8")
    return data_dir


def test_bootstrap_registers_domains_before_channel_defaults(hub_data: Path) -> None:
    ensure_runtime_bootstrap(hub_data)
    assert ConfigRegistry.get("agent.wechat.workbench") is not None
    assert ConfigRegistry.get("agent.douyin.workbench") is not None
    snap = ConfigManager.get().read("agent.wechat.workbench")
    assert isinstance(snap, dict)


def test_patch_domain_uses_replace_not_yaml_fallback(
    hub_data: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ensure_runtime_bootstrap(hub_data)
    from plugins.mxai.wizard.channel_defaults import _patch_domain

    with caplog.at_level(logging.ERROR, logger="plugins.mxai.wizard.channel_defaults"):
        _patch_domain(
            "wechat",
            "workbench",
            {"inbound_reply": {"enabled": True}},
            merge_mode="missing",
        )
    assert not any("yaml-only fallback" in r.message for r in caplog.records)
    wb = ConfigManager.get().read("agent.wechat.workbench") or {}
    assert (wb.get("inbound_reply") or {}).get("enabled") is True
