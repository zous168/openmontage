"""分渠道按工作业务 Agent 绑定（Untitled-1）."""

from __future__ import annotations

from plugins.mxai.cfg.agent_bindings import (
    AGENT_BOSS_DM,
    AGENT_BOSS_RESUME,
    AGENT_DOUYIN_COMMENT,
    AGENT_DOUYIN_DM,
    AGENT_WECHAT_CHAT,
    BUSINESS_AGENT_IDS,
    default_agent_bindings,
    normalize_agent_bindings,
    resolve_bound_hermes_profile,
)


def test_business_agent_ids_cover_untitled1():
    assert "wechat_chat" in BUSINESS_AGENT_IDS
    assert "qiyeweixin_chat" in BUSINESS_AGENT_IDS
    assert "douyin_comment" in BUSINESS_AGENT_IDS
    assert "douyin_dm" in BUSINESS_AGENT_IDS
    assert "boss_resume" in BUSINESS_AGENT_IDS
    assert len(BUSINESS_AGENT_IDS) == 10


def test_default_bindings_per_channel():
    assert default_agent_bindings("wechat")["modules"]["inbound_reply"] == AGENT_WECHAT_CHAT
    assert default_agent_bindings("douyin")["modules"]["comment_reply"] == AGENT_DOUYIN_COMMENT
    assert default_agent_bindings("douyin")["modules"]["dm"] == AGENT_DOUYIN_DM
    assert default_agent_bindings("boss")["modules"]["inbound_reply"] == AGENT_BOSS_DM
    assert default_agent_bindings("boss")["modules"]["resume"] == AGENT_BOSS_RESUME


def test_normalize_rejects_cross_channel_and_legacy_keys():
    n = normalize_agent_bindings(
        {"modules": {"inbound_reply": "douyin_dm", "first_comment": "first_comment"}},
        channel_id="wechat",
    )
    assert n["modules"]["inbound_reply"] == AGENT_WECHAT_CHAT
    assert "first_comment" not in n["modules"]

    d = normalize_agent_bindings(
        {"modules": {"first_comment": "first_comment", "dm": "wechat_chat"}},
        channel_id="douyin",
    )
    assert d["modules"]["first_comment"] == AGENT_DOUYIN_COMMENT
    assert d["modules"]["dm"] == AGENT_DOUYIN_DM


def test_cron_hermes_profile_by_feature():
    boss_wb = {
        "agent_bindings": {
            "default": AGENT_BOSS_DM,
            "modules": {
                "inbound_reply": AGENT_BOSS_DM,
                "resume": AGENT_BOSS_RESUME,
            },
        }
    }
    from plugins.mxai.cfg.agent_bindings import cron_hermes_profile

    assert cron_hermes_profile("boss", "boss_proactive_dm", workbench=boss_wb) == AGENT_BOSS_DM
    assert cron_hermes_profile("boss", "boss_greet_schedule", workbench=boss_wb) == AGENT_BOSS_RESUME
    assert cron_hermes_profile("douyin", "benchmark_monitor") == AGENT_DOUYIN_COMMENT
    assert cron_hermes_profile("douyin", "first_comment_daily") == AGENT_DOUYIN_COMMENT


def test_resolve_bound_hermes_profile_from_workbench():
    wb = {
        "agent_bindings": {
            "default": AGENT_DOUYIN_COMMENT,
            "modules": {
                "comment_reply": AGENT_DOUYIN_COMMENT,
                "first_comment": AGENT_DOUYIN_COMMENT,
                "dm": AGENT_DOUYIN_DM,
            },
        }
    }
    assert resolve_bound_hermes_profile("douyin", "dm", workbench=wb) == AGENT_DOUYIN_DM
    assert (
        resolve_bound_hermes_profile("douyin", "comment_reply", workbench=wb)
        == AGENT_DOUYIN_COMMENT
    )
