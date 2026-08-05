"""m0011 · 渠道 cron 补迁至业务 Agent."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.mxai.cfg.agent_bindings import agent_profile_for_channel
from plugins.mxai.cfg.migrations.m0011_cron_channel_to_business_agent import MIGRATION
from plugins.mxai.cfg.paths import state_path


def test_m0011_migrates_cron_from_m0007_backup(tmp_path: Path):
    data_dir = tmp_path
    cid = "wechat"
    biz = agent_profile_for_channel(cid)
    backup = state_path("migration_backups/m0007_channel_work_agents", data_dir) / "removed_channel_profiles" / cid
    backup.mkdir(parents=True)
    (backup / "cron").mkdir()
    jobs = {"jobs": [{"id": "legacy-job", "name": "旧渠道 job", "prompt": "x", "schedule": "every 1h"}]}
    (backup / "cron" / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")

    (data_dir / "profiles" / biz).mkdir(parents=True)

    changed = MIGRATION.apply(data_dir)
    assert changed >= 1

    dest = data_dir / "profiles" / biz / "cron" / "jobs.json"
    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert any(j["id"] == "legacy-job" for j in loaded["jobs"])

    again = MIGRATION.apply(data_dir)
    assert again == 0


def test_m0011_channel_still_present(tmp_path: Path):
    data_dir = tmp_path
    cid = "douyin"
    biz = agent_profile_for_channel(cid)
    ch = data_dir / "profiles" / cid
    ch.mkdir(parents=True)
    (ch / "cron").mkdir()
    (ch / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": [{"id": "mxai-douyin-benchmark_monitor", "name": "t"}]}),
        encoding="utf-8",
    )
    (data_dir / "profiles" / biz).mkdir(parents=True)

    assert MIGRATION.apply(data_dir) >= 1
    dest = json.loads((data_dir / "profiles" / biz / "cron" / "jobs.json").read_text(encoding="utf-8"))
    assert any(j["id"] == "mxai-douyin-benchmark_monitor" for j in dest["jobs"])
