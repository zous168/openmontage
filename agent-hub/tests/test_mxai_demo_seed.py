"""演示数据种子测试."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.demo_seed import DEMO_PREFIX, seed_demo_data
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap


@pytest.fixture
def demo_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub_data"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    main = profiles / "main"
    main.mkdir()
    (main / "config.yaml").write_text("model: test\n", encoding="utf-8")

    def fake_create(name: str, **kwargs: object) -> Path:
        d = profiles / name
        d.mkdir(parents=True, exist_ok=True)
        if not (d / "config.yaml").exists():
            (d / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return d

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (profiles / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    ensure_runtime_bootstrap(data_dir)
    return data_dir


def test_seed_demo_data_idempotent(demo_data_dir: Path) -> None:
    first = seed_demo_data(demo_data_dir)
    assert first.status == "seeded"
    assert first.counts.get("worklogs", 0) >= 20

    second = seed_demo_data(demo_data_dir)
    assert second.status == "skipped"

    conn = sqlite3.connect(mxai_db_path("hub.db", demo_data_dir))  # LT-033：work_logs 并入 hub.db
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM work_logs WHERE log_id LIKE ?",
            (f"{DEMO_PREFIX}%",),
        ).fetchone()
        assert int(row[0]) >= 20
    finally:
        conn.close()


def test_seed_demo_force_refresh(demo_data_dir: Path) -> None:
    seed_demo_data(demo_data_dir)
    again = seed_demo_data(demo_data_dir, force=True)
    assert again.status == "seeded"

    QueueManager.reset()
    seed_demo_data(demo_data_dir, force=True)
    listed = QueueManager.get().list_tasks(page=1, page_size=100)
    demo_count = sum(
        1 for item in listed["items"] if str(item["task_id"]).startswith(DEMO_PREFIX)
    )
    assert demo_count == 8

    conn = sqlite3.connect(mxai_db_path("hub.db", demo_data_dir))
    try:
        leads = conn.execute(
            """
            SELECT COUNT(*) FROM douyin_leads WHERE lead_id LIKE ?
            UNION ALL
            SELECT COUNT(*) FROM xiaohongshu_leads WHERE lead_id LIKE ?
            UNION ALL
            SELECT COUNT(*) FROM shipinhao_leads WHERE lead_id LIKE ?
            """,
            (f"{DEMO_PREFIX}%", f"{DEMO_PREFIX}%", f"{DEMO_PREFIX}%"),
        ).fetchall()
        assert sum(int(r[0]) for r in leads) == 6
    finally:
        conn.close()
