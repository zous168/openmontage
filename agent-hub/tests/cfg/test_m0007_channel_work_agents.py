"""m0007 · 分渠道业务 Agent 绑定与 profile 骨架."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from plugins.mxai.cfg.agent_bindings import (
    BUSINESS_AGENT_IDS,
    agent_profile_for_channel,
    default_agent_bindings,
)
from plugins.mxai.cfg.migrations.m0007_channel_work_agents import MIGRATION


def test_m0007_writes_bindings_and_business_profiles(tmp_path: Path):
    data_dir = tmp_path
    # 渠道壳 + 假 config，供业务 Agent clone
    for cid in ("wechat", "douyin", "boss"):
        p = data_dir / "profiles" / cid
        p.mkdir(parents=True)
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "SOUL.md").write_text("# channel soul\n", encoding="utf-8")
        cfg_dir = data_dir / "plugins" / "mxai" / "cfg" / cid
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "workbench.yaml").write_text("inbound_reply:\n  enabled: true\n", encoding="utf-8")

    changed = MIGRATION.apply(data_dir)
    assert changed > 0

    for cid in ("wechat", "douyin", "boss"):
        wb_path = data_dir / "plugins" / "mxai" / "cfg" / cid / "workbench.yaml"
        wb = yaml.safe_load(wb_path.read_text(encoding="utf-8"))
        assert wb["agent_bindings"] == default_agent_bindings(cid)
        assert not (data_dir / "profiles" / cid / "SOUL.md").is_file()

    for pid in BUSINESS_AGENT_IDS:
        assert (data_dir / "profiles" / pid).is_dir()

    again = MIGRATION.apply(data_dir)
    assert again == 0


def test_m0007_migrates_channel_cron_to_business_agent(tmp_path: Path):
    data_dir = tmp_path
    cid = "wechat"
    biz = agent_profile_for_channel(cid)
    channel_home = data_dir / "profiles" / cid
    channel_home.mkdir(parents=True)
    (channel_home / "config.yaml").write_text("model: test\n", encoding="utf-8")
    cron_dir = channel_home / "cron"
    cron_dir.mkdir()
    jobs = {
        "jobs": [
            {
                "id": "mxai-wechat-scheduled_touch",
                "name": "微信·存量定时触达",
                "http": {
                    "url": f"http://127.0.0.1:8642/api/plugins/mxai/cron/run/scheduled_touch/{cid}",
                },
            },
            {"id": "user-custom-job", "name": "用户自建", "prompt": "ping", "schedule": "every 30m"},
        ],
    }
    (cron_dir / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    out_dir = cron_dir / "output" / "user-custom-job"
    out_dir.mkdir(parents=True)
    (out_dir / "2026-07-01.md").write_text("# ok\n", encoding="utf-8")

    cfg_dir = data_dir / "plugins" / "mxai" / "cfg" / cid
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "workbench.yaml").write_text("inbound_reply:\n  enabled: true\n", encoding="utf-8")

    MIGRATION.apply(data_dir)

    dest_jobs = data_dir / "profiles" / biz / "cron" / "jobs.json"
    assert dest_jobs.is_file()
    loaded = json.loads(dest_jobs.read_text(encoding="utf-8"))
    ids = {j["id"] for j in loaded["jobs"]}
    assert "mxai-wechat-scheduled_touch" in ids
    assert "user-custom-job" in ids
    assert (data_dir / "profiles" / biz / "cron" / "output" / "user-custom-job" / "2026-07-01.md").is_file()
    assert not channel_home.is_dir()
