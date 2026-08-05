"""Hermes Dashboard Profile 记忆只读 API."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hermes_cli.memory_profile import (
    get_profile_memory_overview,
    list_profile_agent_sessions,
    list_profile_holographic_entities,
    list_profile_holographic_facts,
    purge_profile_noise_entities,
    purge_profile_transient_memory,
    simulate_profile_memory_retrieval,
)


@pytest.fixture
def profile_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profile_dir = data_dir / "profiles" / "douyin"
    profile_dir.mkdir(parents=True)
    mem_dir = profile_dir / "memories"
    mem_dir.mkdir()
    (mem_dir / "MEMORY.md").write_text("渠道话术\n§\n短评", encoding="utf-8")
    (mem_dir / "USER.md").write_text("运营偏好简洁", encoding="utf-8")
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "memory": {
                    "provider": "holographic",
                    "memory_enabled": True,
                    "user_profile_enabled": True,
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    db = profile_dir / "memory_store.db"
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir if name == "default" else data_dir / "profiles" / name,
    )
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: profile_dir)
    from plugins.memory.holographic.store import MemoryStore as HolographicStore

    holo = HolographicStore(db_path=str(db))
    holo.add_fact("运营偏好简洁", category="user_pref")
    holo.add_fact('平台 "Douyin" 的评论风格规则', category="general")
    holo.add_fact("Douyin short comment style rules", category="general")
    holo.close()
    return profile_dir


def test_overview_scoped_to_profile_home(profile_home: Path) -> None:
    overview = get_profile_memory_overview(home=profile_home, profile_label="douyin")
    assert overview["profile_id"] == "douyin"
    assert overview["provider"] == "holographic"
    assert overview["settings"]["prefetch_limit"] == 5
    assert overview["settings"]["memory_enabled"] is True
    assert overview["stats"]["holographic_facts"] == 3
    assert overview["stats"]["memory_md_entries"] == 2


def test_facts_list(profile_home: Path) -> None:
    page = list_profile_holographic_facts(home=profile_home, limit=10)
    assert page["total"] == 3


def test_entities_list(profile_home: Path) -> None:
    page = list_profile_holographic_entities(home=profile_home, limit=50)
    assert page["total"] >= 1
    assert page["usable"] >= 1
    names = {e["name"] for e in page["entities"]}
    assert "Douyin" in names
    douyin = next(e for e in page["entities"] if e["name"] == "Douyin")
    assert douyin["fact_count"] >= 1
    assert douyin["plausible"] is True


def test_purge_noise_entities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: profile_dir)
    from plugins.memory.holographic.store import MemoryStore

    db_path = profile_dir / "memory_store.db"
    store = MemoryStore(db_path=str(db_path))
    store.add_fact('平台 "Douyin" 规则', category="general")
    store.close()

    # Simulate legacy junk already in DB (before extraction filter existed).
    conn = __import__("sqlite3").connect(db_path)
    conn.execute("INSERT INTO entities (name) VALUES (?)", ("cd: No such file or directory",))
    conn.commit()
    conn.close()

    before = list_profile_holographic_entities(home=profile_dir)
    assert before["noise"] >= 1
    assert before["usable"] >= 1

    result = purge_profile_noise_entities(home=profile_dir)
    assert result["count"] >= 1
    assert "cd: No such file or directory" in result["removed"]

    after = list_profile_holographic_entities(home=profile_dir)
    assert after["noise"] == 0
    assert any(e["name"] == "Douyin" for e in after["entities"])


def test_list_profile_agent_sessions_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: profile_dir)
    page = list_profile_agent_sessions(home=profile_dir)
    assert page["total"] == 0
    assert page["sessions"] == []


def test_purge_transient_memory_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_dir = tmp_path / "profile"
    mem_dir = profile_dir / "memories"
    mem_dir.mkdir(parents=True)
    wsl = (
        "The terminal tool runs inside WSL. Project path H:\\work must use /mnt/h/work. "
        "read_file tool cannot resolve paths — use cat via terminal."
    )
    stable = "用户负责抖音业务（抖音渠道运营）。"
    (mem_dir / "MEMORY.md").write_text(f"{wsl}\n§\n{stable}", encoding="utf-8")
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: profile_dir)

    overview = get_profile_memory_overview(home=profile_dir)
    assert overview["stats"]["memory_md_transient"] == 1

    result = purge_profile_transient_memory(home=profile_dir, target="memory")
    assert result["count"] == 1
    assert stable in (profile_dir / "memories" / "MEMORY.md").read_text(encoding="utf-8")
    assert "WSL" not in (profile_dir / "memories" / "MEMORY.md").read_text(encoding="utf-8")


def test_retrieve_session_start_blocks(profile_home: Path) -> None:
    result = simulate_profile_memory_retrieval(
        home=profile_home,
        profile_label="douyin",
        query="渠道话术怎么写",
    )
    session = result["scenario"]["session_start"]
    assert "渠道话术" in (session["memory_block"] or "")
    assert "运营偏好简洁" in (session["user_block"] or "")
    assert session.get("holographic_system_block")
    assert "Holographic Memory" in session["holographic_system_block"]
    assert "session_start" in result["scenario"]
    assert "turn_prefetch" in result["scenario"]
    assert "conversation_history" in result["scenario"]
    assert "fact_store_search" not in result["scenario"]


def test_retrieve_holographic_prefetch(profile_home: Path) -> None:
    result = simulate_profile_memory_retrieval(
        home=profile_home,
        profile_label="douyin",
        query="Douyin comment rules",
    )
    assert result["scenario"]["turn_prefetch"]["facts"]
    assert result["scenario"]["turn_prefetch"]["limit"] == 5


def test_retrieve_holographic_prefetch_respects_config(profile_home: Path) -> None:
    cfg_path = profile_home / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["memory"]["prefetch_limit"] = 2
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    result = simulate_profile_memory_retrieval(
        home=profile_home,
        profile_label="douyin",
        query="Douyin comment rules",
    )
    assert result["scenario"]["turn_prefetch"]["limit"] == 2
    assert len(result["scenario"]["turn_prefetch"]["facts"]) <= 2
    assert result["settings"]["prefetch_limit"] == 2
