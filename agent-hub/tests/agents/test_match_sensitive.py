"""敏感词入站匹配：UI ``black`` 与旧 ``words`` 兼容。"""

from __future__ import annotations

from pathlib import Path

import yaml

from plugins.mxai.agents import pipeline as pipeline_mod


def _write_sensitive(tmp_path: Path, profile_id: str, data: dict) -> None:
    cfg_dir = tmp_path / "plugins" / "mxai" / "cfg" / profile_id
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "sensitive_words.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_match_sensitive_reads_black(tmp_path, monkeypatch):
    _write_sensitive(
        tmp_path,
        "boss",
        {"black": ["互联网", "销售"], "white": [], "strategy": "block", "enabled": True},
    )
    monkeypatch.setattr(
        pipeline_mod,
        "agent_cfg_path",
        lambda pid, filename: tmp_path / "plugins" / "mxai" / "cfg" / pid / filename,
    )
    monkeypatch.setattr(pipeline_mod, "newest_existing", lambda *paths: next((p for p in paths if p.is_file()), None))
    msg = "你好，我想了解一下销售岗位，以及互联网相关的工作机会。"
    assert pipeline_mod._match_sensitive("boss", msg) in {"销售", "互联网"}


def test_match_sensitive_legacy_words(tmp_path, monkeypatch):
    _write_sensitive(tmp_path, "wechat", {"words": ["违禁词"]})
    monkeypatch.setattr(
        pipeline_mod,
        "agent_cfg_path",
        lambda pid, filename: tmp_path / "plugins" / "mxai" / "cfg" / pid / filename,
    )
    monkeypatch.setattr(pipeline_mod, "newest_existing", lambda *paths: next((p for p in paths if p.is_file()), None))
    assert pipeline_mod._match_sensitive("wechat", "含违禁词的消息") == "违禁词"


def test_match_sensitive_disabled(tmp_path, monkeypatch):
    _write_sensitive(
        tmp_path,
        "boss",
        {"black": ["销售"], "enabled": False},
    )
    monkeypatch.setattr(
        pipeline_mod,
        "agent_cfg_path",
        lambda pid, filename: tmp_path / "plugins" / "mxai" / "cfg" / pid / filename,
    )
    monkeypatch.setattr(pipeline_mod, "newest_existing", lambda *paths: next((p for p in paths if p.is_file()), None))
    assert pipeline_mod._match_sensitive("boss", "销售岗位") is None
