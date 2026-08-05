"""cs_peer_manager：session id 与 profile 引导（无硬编码 SOUL）."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli.cs_peer_manager import cs_sim_session_id, ensure_profile


def test_cs_sim_session_id_stable() -> None:
    a = cs_sim_session_id("customer", "web", "peer-1")
    b = cs_sim_session_id("customer", "web", "peer-1")
    c = cs_sim_session_id("customer", "wechat", "peer-1")
    assert a == b
    assert a.startswith("mxai-customer-inbound-")
    assert a != c


def test_ensure_profile_does_not_write_hardcoded_soul(tmp_path: Path, monkeypatch) -> None:
    profile_root = tmp_path / "profiles" / "customer"
    profile_root.mkdir(parents=True)
    default_home = tmp_path / "default"
    default_home.mkdir()
    (default_home / "config.yaml").write_text("agent: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profile_root if name == "customer" else default_home,
    )
    monkeypatch.setattr(
        "hermes_constants.get_default_hermes_root",
        lambda: default_home,
    )

    ensure_profile("customer")
    soul = profile_root / "SOUL.md"
    assert not soul.exists() or "企业官方智能客服" not in soul.read_text(encoding="utf-8")
