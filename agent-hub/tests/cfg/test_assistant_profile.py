"""assistant Profile 运行时 bootstrap."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.cfg.bootstrap.assistant_profile import (
    apply_business_agent_api_toolsets,
    assistant_profile_ready,
    ensure_assistant_profile_runtime,
    ensure_channel_kb_search_toolset,
    ensure_chat_agent_toolsets,
)
from plugins.mxai.mcp_tools import MXAI_PER_TOOL_TOOLSETS, MXAI_TOOLSET
from plugins.mxai.cfg.store import atomic_write_yaml, read_yaml


def test_ensure_chat_agent_toolsets_kb_only(tmp_path: Path) -> None:
    """私域聊天 Agent：api_server = mxai_kb_search + skills_view（仅 skill_view）。"""
    profile_dir = tmp_path / "qiyeweixin_chat"
    profile_dir.mkdir()
    cp = profile_dir / "config.yaml"
    atomic_write_yaml(
        cp,
        {
            "platform_toolsets": {
                "api_server": [
                    "hermes-api-server",
                    "mxai_kb_search",
                    "file",
                    "skills",
                ]
            }
        },
    )
    assert ensure_chat_agent_toolsets(profile_dir, "qiyeweixin_chat") == "chat_toolsets"
    api = read_yaml(cp)["platform_toolsets"]["api_server"]
    assert api == ["mxai_kb_search", "skills_view"]
    assert ensure_chat_agent_toolsets(profile_dir, "qiyeweixin_chat") == "skipped"


def test_chat_agent_toolsets_resolve_to_kb_and_skill_view_only(tmp_path: Path) -> None:
    from hermes_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset

    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    atomic_write_yaml(
        profile_dir / "config.yaml",
        {"platform_toolsets": {"api_server": ["mxai_kb_search", "skills_view"]}},
    )
    cfg = read_yaml(profile_dir / "config.yaml")
    enabled = _get_platform_tools(cfg, "api_server", include_default_mcp_servers=False)
    assert "skills_view" in enabled
    assert "skills" not in enabled
    tool_names = set()
    for ts in enabled:
        tool_names.update(resolve_toolset(ts))
    assert tool_names == {"mxai_kb_search", "skill_view"}


def test_apply_business_agent_api_toolsets_routes_chat(tmp_path: Path) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    cp = profile_dir / "config.yaml"
    atomic_write_yaml(
        cp,
        {"platform_toolsets": {"api_server": ["hermes-api-server", "mxai"]}},
    )
    assert apply_business_agent_api_toolsets(profile_dir, "wechat_chat") == "chat_toolsets"
    assert read_yaml(cp)["platform_toolsets"]["api_server"] == ["mxai_kb_search", "skills_view"]


def test_ensure_channel_kb_search_toolset(tmp_path: Path) -> None:
    """CR-125 · FR-KB-20：业务渠道 Profile 仅保留 mxai_kb_search，剥离整包 mxai。"""
    profile_dir = tmp_path / "douyin"
    profile_dir.mkdir()
    cp = profile_dir / "config.yaml"
    # 无 config → 跳过
    assert ensure_channel_kb_search_toolset(profile_dir) == "skipped"
    # 有 config 无 toolset → 加 mxai_kb_search（不授其它编排工具）
    atomic_write_yaml(cp, {"platform_toolsets": {"api_server": ["hermes-api-server"]}})
    assert ensure_channel_kb_search_toolset(profile_dir) == "kb_search_toolset"
    api = read_yaml(cp)["platform_toolsets"]["api_server"]
    assert "mxai_kb_search" in api
    assert "mxai_queue_enqueue" not in api  # 仅 KB 工具
    # 幂等
    assert ensure_channel_kb_search_toolset(profile_dir) == "skipped"
    # 整包 mxai → 收成仅 mxai_kb_search（保留非 MxAI toolset）
    atomic_write_yaml(
        cp,
        {"platform_toolsets": {"api_server": ["browser", "mxai", "web"]}},
    )
    assert ensure_channel_kb_search_toolset(profile_dir) == "kb_search_toolset"
    api = read_yaml(cp)["platform_toolsets"]["api_server"]
    assert api == ["browser", "web", "mxai_kb_search"]
    assert ensure_channel_kb_search_toolset(profile_dir) == "skipped"


def test_ensure_assistant_profile_runtime_idempotent(tmp_path: Path) -> None:
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir()
    (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")

    first = ensure_assistant_profile_runtime(profile_dir)
    second = ensure_assistant_profile_runtime(profile_dir)
    assert first == "patched"
    assert second == "skipped"

    cfg = read_yaml(profile_dir / "config.yaml")
    api_list = cfg["platform_toolsets"]["api_server"]
    assert MXAI_TOOLSET in api_list or all(k in api_list for k in MXAI_PER_TOOL_TOOLSETS)
    soul = (profile_dir / "SOUL.md").read_text(encoding="utf-8")
    assert "本机文件预览" in soul
    assert "MEDIA:" in soul
    assert assistant_profile_ready(profile_dir)


def test_assistant_ready_ignores_soul_wording(tmp_path: Path) -> None:
    """就绪只看文件与 toolset，不依赖 SOUL 里是否含 MxAI A-Main."""
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir()
    atomic_write_yaml(
        profile_dir / "config.yaml",
        {"platform_toolsets": {"api_server": ["hermes-api-server", *MXAI_PER_TOOL_TOOLSETS, "messaging"]}},
    )
    (profile_dir / "SOUL.md").write_text(
        "You are Hermes Agent, an intelligent AI assistant.\n",
        encoding="utf-8",
    )
    (profile_dir / "INSTRUCTIONS.md").write_text("## 铁律\nkeep me\n", encoding="utf-8")
    assert assistant_profile_ready(profile_dir)


def test_patch_assistant_soul_local_preview_idempotent(tmp_path: Path) -> None:
    from plugins.mxai.cfg.prompt_config import patch_assistant_soul_local_preview

    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir()
    (profile_dir / "SOUL.md").write_text("# MxAI A-Main\n", encoding="utf-8")
    assert patch_assistant_soul_local_preview(profile_dir) == "patched"
    assert patch_assistant_soul_local_preview(profile_dir) == "skipped"
    assert "MEDIA:" in (profile_dir / "SOUL.md").read_text(encoding="utf-8")


def test_assistant_chat_self_heals_missing_profile(mxai_client, tmp_path: Path) -> None:
    """目录被删时聊天路径会 ensure 补齐，不再因 SOUL 字样卡死。"""
    import shutil

    from hermes_cli.profiles import get_profile_dir

    assistant_dir = get_profile_dir("assistant")
    if assistant_dir.is_dir():
        shutil.rmtree(assistant_dir)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "你好", "agent": "assistant", "stream": False},
    ).json()
    assert body.get("reply", {}).get("error") != "assistant_profile_not_ready"
    assert assistant_dir.is_dir()
    assert assistant_profile_ready(assistant_dir)
