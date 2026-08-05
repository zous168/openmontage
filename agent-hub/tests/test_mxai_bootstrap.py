"""MxAI 插件 bootstrap 与注册表单元测试."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.cfg.bootstrap.bootstrap_state import get_last_bootstrap_report
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.registry.databases import DatabaseRegistry


@pytest.fixture
def isolated_hub_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub_data"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles_root = data_dir / "profiles"
    profiles_root.mkdir()
    # 预置 main 供 clone_from 使用
    main_dir = profiles_root / "main"
    main_dir.mkdir()
    (main_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
    return data_dir


@pytest.fixture(autouse=True)
def reset_registries() -> None:
    AgentRegistry.clear()
    from plugins.mxai._bootstrap_imports import load_registries
    from plugins.mxai.agents._register import register_channel_agents

    load_registries()
    register_channel_agents()
    yield
    AgentRegistry.clear()


def test_agent_registry_has_eight_profiles() -> None:
    ids = {a.profile_id for a in AgentRegistry.all()}
    assert ids == {
        "assistant",
        "main",
        "douyin",
        "xiaohongshu",
        "shipinhao",
        "wechat",
        "qiyeweixin",
        "boss",
    }


def test_agent_registry_bootstrap_order() -> None:
    ids = [a.profile_id for a in AgentRegistry.all()]
    assert ids.index("main") < ids.index("assistant")
    assert AgentRegistry.get("assistant").clone_from == "main"


def test_database_registry_databases() -> None:
    # LT-033：worklog.db + report.db 已并入 hub.db
    files = {d.file for d in DatabaseRegistry.all()}
    assert files == {"hub.db", "kb.db", "materials.db"}


def test_ensure_runtime_bootstrap_creates_databases(
    isolated_hub_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_profile(name: str, **kwargs: object) -> Path:
        profile_dir = isolated_hub_data_dir / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        if not (profile_dir / "config.yaml").exists():
            (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return profile_dir

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create_profile)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (isolated_hub_data_dir / "profiles" / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: isolated_hub_data_dir / "profiles" / name,
    )

    report = ensure_runtime_bootstrap(isolated_hub_data_dir)
    assert report.checked_at
    assert len(report.databases) == 3  # LT-033：hub.db + kb.db + materials.db
    for db in report.databases:
        assert db.status in {"initialized", "skipped", "migrated"}
        assert mxai_db_path(db.file, isolated_hub_data_dir).is_file()

    conn = sqlite3.connect(mxai_db_path("hub.db", isolated_hub_data_dir))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "work_logs" in tables
        assert "schema_migrations" in tables
    finally:
        conn.close()

    bootstrap_file = isolated_hub_data_dir / ".mxai_bootstrap.json"
    assert bootstrap_file.is_file()
    assert get_last_bootstrap_report() is not None


def test_assistant_profile_skips_mxai_cfg_seed(
    isolated_hub_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_profile(name: str, **kwargs: object) -> Path:
        profile_dir = isolated_hub_data_dir / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        if not (profile_dir / "config.yaml").exists():
            (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return profile_dir

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create_profile)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (isolated_hub_data_dir / "profiles" / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: isolated_hub_data_dir / "profiles" / name,
    )

    report = ensure_runtime_bootstrap(isolated_hub_data_dir)
    by_id = {p.id: p for p in report.profiles}
    assert by_id["assistant"].cfg in {"skipped", "assistant_runtime"}
    assert by_id["main"].cfg in {"seeded", "skipped"}

    assistant_dir = isolated_hub_data_dir / "profiles" / "assistant"
    main_dir = isolated_hub_data_dir / "profiles" / "main"
    assert not (assistant_dir / "faq.yaml").exists()
    assert not (assistant_dir / "risk.yaml").exists()
    assert (main_dir / "faq.yaml").is_file() or (main_dir / "risk.yaml").is_file()


def test_assistant_profile_enables_mxai_toolset(
    isolated_hub_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_profile(name: str, **kwargs: object) -> Path:
        profile_dir = isolated_hub_data_dir / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        if not (profile_dir / "config.yaml").exists():
            (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return profile_dir

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create_profile)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (isolated_hub_data_dir / "profiles" / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: isolated_hub_data_dir / "profiles" / name,
    )

    ensure_runtime_bootstrap(isolated_hub_data_dir)
    assistant_dir = isolated_hub_data_dir / "profiles" / "assistant"
    cfg_text = (assistant_dir / "config.yaml").read_text(encoding="utf-8")
    # 新 Profile 授现代 granular per-tool 形态（含 mxai_queue_enqueue），
    # 不含 legacy 复合名 ``- mxai``（仅旧 Profile 向后兼容）。
    assert "mxai_queue_enqueue" in cfg_text
    assert "- mxai\n" not in cfg_text
    assert (assistant_dir / "SOUL.md").is_file()


def test_bootstrap_status_route() -> None:
    from plugins.mxai.api.bootstrap import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/mxai")
    client = TestClient(app)

    resp = client.get("/api/plugins/mxai/bootstrap/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
    assert "databases" in body
    assert "profiles" in body
