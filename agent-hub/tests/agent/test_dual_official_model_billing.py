"""回归：全局 Qwen 与渠道壳 MiniMax 并存 → CS 流水可同时出现两种 model。

现象（消耗流水）：
  11:27 Token · Qwen3.6-27B · 40
  11:29 Token · MiniMax-M2.7 · 15145

本机对照：
  - 全局 / 聊天 Agent ``qiyeweixin_chat``：跟随系统 → Qwen
  - 企微 Gateway ``HERMES_HOME=profiles/qiyeweixin``：独立绑定 official+MiniMax
  Hub 入站走 chat profile；Gateway 进程读渠道壳 config → 同窗口两种计费 model。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _read_model_under_home(home: Path) -> tuple[str, str]:
    from hermes_cli.config import invalidate_config_caches, load_config
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(home))
    try:
        invalidate_config_caches()
        cfg = load_config() or {}
        m = cfg.get("model") or {}
        if isinstance(m, str):
            return "", m
        if isinstance(m, dict):
            return str(m.get("provider") or ""), str(m.get("default") or m.get("model") or "")
        return "", ""
    finally:
        reset_hermes_home_override(token)
        invalidate_config_caches()


@pytest.fixture()
def dual_model_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """数据根 = Qwen；渠道壳 qiyeweixin = MiniMax；聊天 Agent 无本地 model。"""
    root = tmp_path / "data"
    root.mkdir()
    _write_yaml(
        root / "config.yaml",
        {"model": {"provider": "official", "default": "Qwen3.6-27B"}},
    )
    channel = root / "profiles" / "qiyeweixin"
    _write_yaml(
        channel / "config.yaml",
        {"model": {"provider": "official", "default": "MiniMax-M2.7"}},
    )
    chat = root / "profiles" / "qiyeweixin_chat"
    _write_yaml(chat / "config.yaml", {"agent": {"max_turns": 90}})  # 无 model → 继承全局

    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    monkeypatch.setenv("HERMES_HOME", str(root))
    # get_default_hermes_root 读环境 / 常量；覆盖 base 解析
    monkeypatch.setattr(
        "hermes_constants.get_default_hermes_root",
        lambda: root,
    )
    try:
        monkeypatch.setattr(
            "hermes_cli.config.get_default_hermes_root",
            lambda: root,
        )
    except Exception:
        pass
    from hermes_cli.config import invalidate_config_caches

    invalidate_config_caches()
    return {"root": root, "channel": channel, "chat": chat}


def test_wecom_gateway_shell_keeps_minimax_while_chat_inherits_qwen(dual_model_homes):
    """挂着 Qwen（全局/聊天）时，渠道壳 Gateway 仍会解析出 MiniMax → CS 双 model。"""
    root = dual_model_homes["root"]
    channel = dual_model_homes["channel"]
    chat = dual_model_homes["chat"]

    gp, gm = _read_model_under_home(root)
    assert (gp, gm) == ("official", "Qwen3.6-27B")

    cp, cm = _read_model_under_home(channel)
    assert (cp, cm) == ("official", "MiniMax-M2.7"), (
        "企微 Gateway hermes_home=profiles/qiyeweixin 应仍为 MiniMax；"
        f"实际 {(cp, cm)} — 若此处不是 MiniMax，则流水双计费另有来源"
    )

    hp, hm = _read_model_under_home(chat)
    assert hm == "Qwen3.6-27B", (
        "qiyeweixin_chat 无本地 model 时应 overlay 全局 Qwen；"
        f"实际 provider={hp!r} model={hm!r}"
    )
    # 同一「企微」产品下两套 profile 解析出两个官方模型 → 流水可同时出现两者
    assert cm != hm


def test_clear_legacy_channel_shell_models_makes_gateway_follow_global(dual_model_homes, monkeypatch):
    """修复后：清掉渠道壳 model，Gateway home 与聊天 Agent 一样跟随全局 Qwen。"""
    from plugins.mxai.cfg.agent_model_config import clear_legacy_channel_shell_models

    root = dual_model_homes["root"]
    channel = dual_model_homes["channel"]
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: root / "profiles" / pid,
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda pid: root / "profiles" / pid,
    )

    cleared = clear_legacy_channel_shell_models()
    assert "qiyeweixin" in cleared

    from hermes_cli.profiles import _read_config_model

    local_m, local_p = _read_config_model(channel)
    assert local_m is None and local_p is None

    cp, cm = _read_model_under_home(channel)
    assert cm == "Qwen3.6-27B", f"清壳后应跟随全局，实际 {(cp, cm)}"
