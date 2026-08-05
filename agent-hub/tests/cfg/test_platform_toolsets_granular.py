"""Granular per-toolset toggles for api_server (Dashboard Skills / Profile)."""

from __future__ import annotations

import pytest

from plugins.mxai.mcp_tools import MXAI_PER_TOOL_TOOLSETS, MXAI_TOOLSET
from plugins.mxai.cfg.bootstrap.assistant_profile import ensure_assistant_profile_runtime
from plugins.mxai.cfg.store import read_yaml
from hermes_cli.tools_config import (
    _get_platform_tools,
    toggle_dashboard_platform_toolset,
)


@pytest.fixture(autouse=True)
def _no_disk_config_save(monkeypatch: pytest.MonkeyPatch) -> None:
    """toggle_dashboard_platform_toolset persists via save_config — never touch real HUB_DATA_DIR."""
    monkeypatch.setattr("hermes_cli.tools_config.save_config", lambda config: None)


def test_mxai_granular_not_reexpanded_from_composite() -> None:
    config = {
        "platform_toolsets": {
            "api_server": [
                "hermes-api-server",
                MXAI_TOOLSET,
                "mxai_queue_enqueue",
            ],
        },
    }
    enabled = _get_platform_tools(
        config,
        "api_server",
        include_default_mcp_servers=False,
    )
    assert "mxai_queue_enqueue" in enabled
    assert "mxai_queue_pause_all" not in enabled


def test_toggle_mxai_bundle_writes_composite_key() -> None:
    config = {
        "platform_toolsets": {
            "api_server": ["hermes-api-server"],
        },
    }
    toggle_dashboard_platform_toolset(
        config,
        "api_server",
        MXAI_TOOLSET,
        True,
    )
    saved = config["platform_toolsets"]["api_server"]
    assert MXAI_TOOLSET in saved
    assert not any(k in saved for k in MXAI_PER_TOOL_TOOLSETS if k != MXAI_TOOLSET)


def test_toggle_dashboard_only_changes_one_mxai_tool() -> None:
    config = {
        "platform_toolsets": {
            "api_server": ["hermes-api-server", MXAI_TOOLSET],
        },
    }
    toggle_dashboard_platform_toolset(
        config,
        "api_server",
        "mxai_queue_enqueue",
        False,
    )
    saved_mxai = [k for k in config["platform_toolsets"]["api_server"] if "mxai" in k]
    assert MXAI_TOOLSET not in saved_mxai
    assert "mxai_queue_enqueue" not in saved_mxai
    assert "mxai_queue_pause_all" in saved_mxai

    enabled = _get_platform_tools(
        config,
        "api_server",
        include_default_mcp_servers=False,
    )
    assert "mxai_queue_enqueue" not in enabled
    assert "mxai_queue_pause_all" in enabled


def test_toggle_one_mxai_on_from_composite_writes_only_that_tool() -> None:
    config = {
        "platform_toolsets": {
            "api_server": ["hermes-api-server", MXAI_TOOLSET],
        },
    }
    toggle_dashboard_platform_toolset(
        config,
        "api_server",
        "mxai_queue_enqueue",
        True,
    )
    saved_mxai = [k for k in config["platform_toolsets"]["api_server"] if "mxai" in k]
    assert saved_mxai == ["mxai_queue_enqueue"]

    enabled = _get_platform_tools(
        config,
        "api_server",
        include_default_mcp_servers=False,
    )
    assert "mxai_queue_enqueue" in enabled
    assert "mxai_queue_pause_all" not in enabled


def test_toggle_one_mxai_on_from_clean_profile() -> None:
    config = {
        "platform_toolsets": {
            "api_server": ["hermes-api-server"],
        },
    }
    toggle_dashboard_platform_toolset(
        config,
        "api_server",
        "mxai_queue_enqueue",
        True,
    )
    saved_mxai = [k for k in config["platform_toolsets"]["api_server"] if "mxai" in k]
    assert saved_mxai == ["mxai_queue_enqueue"]


def test_assistant_bootstrap_does_not_readd_disabled_mxai_tools(tmp_path) -> None:
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir()
    (profile_dir / "config.yaml").write_text(
        "model: test\nplatform_toolsets:\n  api_server:\n    - hermes-api-server\n    - mxai_queue_enqueue\n",
        encoding="utf-8",
    )
    ensure_assistant_profile_runtime(profile_dir)
    cfg = read_yaml(profile_dir / "config.yaml")
    api_list_after = cfg["platform_toolsets"]["api_server"]
    assert "mxai_queue_enqueue" in api_list_after
    assert "mxai_queue_pause_all" not in api_list_after
    assert MXAI_TOOLSET not in api_list_after
