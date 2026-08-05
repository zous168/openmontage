"""Profile-scoped gateway config loading (api_server assistant toolsets)."""

from __future__ import annotations

import yaml

import gateway.run as gw_run
from agent.profile_scope import hermes_profile_scope
from hermes_cli.tools_config import _get_platform_tools


def test_load_gateway_config_respects_profile_scope(tmp_path, monkeypatch) -> None:
    """Profile 配置覆盖根配置，且聚合 toolset 会展开为具体工具。

    夹具用 ``spotify``（7 个工具的聚合 toolset）。此处原先用 ``mxai``，
    但该 toolset 随 plugins/mxai 一起移除了 —— 被测行为与具体 toolset 无关。
    """
    root = tmp_path / "hub"
    root.mkdir()
    profile_dir = root / "profiles" / "assistant"
    profile_dir.mkdir(parents=True)

    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "platform_toolsets": {
                    "api_server": ["spotify_playback"],
                }
            }
        ),
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "platform_toolsets": {
                    "api_server": ["spotify"],
                }
            }
        ),
        encoding="utf-8",
    )

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))

    from hermes_cli import profiles as prof_mod

    monkeypatch.setattr(prof_mod, "get_profile_dir", lambda name: root / "profiles" / name)

    with hermes_profile_scope(profile_dir):
        cfg = gw_run._load_gateway_config()
        enabled = _get_platform_tools(cfg, "api_server")
        spotify_keys = {x for x in enabled if x.startswith("spotify")}
        # 聚合 toolset 展开：profile 只写了 "spotify"，应得到全部子工具。
        assert "spotify_search" in spotify_keys
        assert "spotify_queue" in spotify_keys

    # 退出 profile 作用域后回到根配置：只有显式列出的那一个。
    root_cfg = gw_run._load_gateway_config()
    root_enabled = _get_platform_tools(root_cfg, "api_server")
    assert "spotify_playback" in root_enabled
    assert "spotify_search" not in root_enabled
