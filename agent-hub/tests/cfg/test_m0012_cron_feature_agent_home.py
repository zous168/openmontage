"""m0012 · 系统 cron 按功能 agent 落盘."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.mxai.cfg.agent_bindings import AGENT_BOSS_DM, AGENT_BOSS_RESUME
from plugins.mxai.cfg.migrations.m0012_cron_feature_agent_home import MIGRATION


def test_m0012_splits_boss_cron_by_feature(tmp_path: Path):
    data_dir = tmp_path
    boss_dm_home = data_dir / "profiles" / AGENT_BOSS_DM
    boss_dm_home.mkdir(parents=True)
    jobs = {
        "jobs": [
            {"id": "mxai-boss-boss_proactive_dm", "name": "dm", "prompt": "x", "schedule": "every 30m"},
            {"id": "mxai-boss-boss_greet_schedule", "name": "greet", "prompt": "x", "schedule": "every 1m"},
        ],
    }
    (boss_dm_home / "cron").mkdir()
    (boss_dm_home / "cron" / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    greet_out = boss_dm_home / "cron" / "output" / "mxai-boss-boss_greet_schedule"
    greet_out.mkdir(parents=True)
    (greet_out / "run.md").write_text("# ok\n", encoding="utf-8")

    cfg = data_dir / "plugins" / "mxai" / "cfg" / "boss"
    cfg.mkdir(parents=True)
    (cfg / "workbench.yaml").write_text(
        "agent_bindings:\n  default: boss_dm\n  modules:\n    inbound_reply: boss_dm\n    resume: boss_resume\n",
        encoding="utf-8",
    )
    (data_dir / "profiles" / AGENT_BOSS_RESUME).mkdir(parents=True)

    changed = MIGRATION.apply(data_dir)
    assert changed >= 1

    dm_jobs = json.loads((boss_dm_home / "cron" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert any(j["id"] == "mxai-boss-boss_proactive_dm" for j in dm_jobs)
    assert not any(j["id"] == "mxai-boss-boss_greet_schedule" for j in dm_jobs)

    resume_jobs = json.loads(
        (data_dir / "profiles" / AGENT_BOSS_RESUME / "cron" / "jobs.json").read_text(encoding="utf-8")
    )["jobs"]
    assert any(j["id"] == "mxai-boss-boss_greet_schedule" for j in resume_jobs)
    assert (
        data_dir / "profiles" / AGENT_BOSS_RESUME / "cron" / "output" / "mxai-boss-boss_greet_schedule" / "run.md"
    ).is_file()

    assert MIGRATION.apply(data_dir) == 0
