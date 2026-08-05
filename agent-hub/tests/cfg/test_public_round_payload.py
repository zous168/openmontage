"""CR-143：公域入队 payload 补齐（手动/链式/queue 与调度器对齐）."""

from __future__ import annotations

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.public_round_payload import (
    enrich_comment_collect_payload,
    enrich_comment_reply_payload,
)
from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture(autouse=True)
def _reset_cfg() -> None:
    ConfigManager.reset()
    QueueManager.reset()
    yield
    ConfigManager.reset()
    QueueManager.reset()


@pytest.fixture
def payload_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
    (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text(
        "search_keywords:\n  - AI\nmatch_keywords:\n  - 多少钱\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {
                "enabled": True,
                "max_videos_per_run": 7,
                "max_customers_per_run": 11,
            },
            "comment_reply": {
                "enabled": True,
                "author_name": "测试号",
                "max_videos_per_run": 5,
                "max_comments_per_run": 9,
            },
        },
    )


def test_enrich_collect_fills_limits_and_match_keywords(payload_env: None) -> None:
    out = enrich_comment_collect_payload("douyin", {"search_keywords": ["AI"]})
    assert out["max_videos_per_run"] == 7
    assert out["max_customers_per_run"] == 11
    assert out["match_keywords"] == ["多少钱"]


def test_enrich_collect_does_not_override_explicit(payload_env: None) -> None:
    out = enrich_comment_collect_payload(
        "douyin",
        {"max_videos_per_run": 2, "match_keywords": ["自定义"]},
    )
    assert out["max_videos_per_run"] == 2
    assert out["match_keywords"] == ["自定义"]


def test_enrich_reply_fills_limits(payload_env: None) -> None:
    out = enrich_comment_reply_payload("douyin", {})
    assert out["max_videos_per_run"] == 5
    assert out["max_comments_per_run"] == 9


def test_queue_enqueue_manual_collect_gets_limits(payload_env: None) -> None:
    q = QueueManager.get()
    q.arm_work()
    task = q.enqueue(
        profile_id="douyin",
        name="手动采集",
        task_type="comment_collect",
        payload={"search_keywords": ["AI"], "source": "manual"},
        bypass_work_armed=True,
    )
    assert task.payload["max_videos_per_run"] == 7
    assert task.payload["max_customers_per_run"] == 11
    assert task.payload["match_keywords"] == ["多少钱"]
