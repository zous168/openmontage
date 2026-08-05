"""统计聚合与 worklog 对齐."""

from plugins.mxai.stats.service import (
    _core_metrics,
    core_rule_by_label,
    stats_summary,
    agent_channel_stats,
)
from plugins.mxai.worklog.service import append_worklog, list_worklogs


def test_stats_summary_core_counts_demo_op_types() -> None:
    append_worklog(
        profile_id="douyin",
        op_type="评论采集",
        exec_status="成功",
        op_object="评论#1",
    )
    append_worklog(
        profile_id="douyin",
        op_type="自动私信发送",
        exec_status="成功",
        op_object="用户@a",
    )
    summary = stats_summary(range_days=7)
    core = {c["label"]: c["value"] for c in summary["core"]}
    assert core["评论抓取总数"] >= 1
    assert core["自动私信发送"] >= 1
    assert "人工接管会话" not in core
    assert "人工办结会话" not in core
    assert summary["acquire_total"] >= 1
    drill = next(c["drill"] for c in summary["core"] if c["label"] == "评论抓取总数")
    assert "comment_collect" in drill["op_types"] or "评论采集" in drill["op_types"]
    assert set(drill["profile_ids"]) == {"douyin", "xiaohongshu", "shipinhao"}
    assert drill["since_days"] == 7


def test_agent_channel_stats_no_fake_reception() -> None:
    append_worklog(
        profile_id="qiyeweixin",
        op_type="AI 自动回复消息",
        exec_status="成功",
        op_object="客户A",
        elapsed_ms=8000,
    )
    s = agent_channel_stats("qiyeweixin")
    assert s["today_reception"] >= 1
    assert s["avg_response_sec"] == 8


def test_core_ai_reply_metrics_channel_scope() -> None:
    """AI 评论回复=公域；AI 自动回复=企微/微信/Boss（不含公域 inbound_reply）."""
    append_worklog(
        profile_id="douyin",
        op_type="comment_reply",
        exec_status="成功",
        op_object="公域评论回复",
    )
    append_worklog(
        profile_id="douyin",
        op_type="inbound_reply",
        exec_status="成功",
        op_object="公域不应计入自动回复 KPI",
    )
    append_worklog(
        profile_id="qiyeweixin",
        op_type="inbound_reply",
        exec_status="成功",
        op_object="企微自动回复",
    )
    append_worklog(
        profile_id="wechat",
        op_type="inbound_reply",
        exec_status="成功",
        op_object="个微自动回复",
    )
    append_worklog(
        profile_id="boss",
        op_type="inbound_reply",
        exec_status="成功",
        op_object="Boss自动回复",
    )
    core = {c["label"]: c["value"] for c in stats_summary(range_days=7)["core"]}
    assert core["AI 评论回复"] >= 1
    assert core["AI 自动回复消息"] >= 3
    scoped = {
        c["label"]: c["value"]
        for c in _core_metrics(
            [
                {"profile_id": "douyin", "op_type": "inbound_reply"},
                {"profile_id": "qiyeweixin", "op_type": "inbound_reply"},
                {"profile_id": "douyin", "op_type": "comment_reply"},
                {"profile_id": "wechat", "op_type": "comment_reply"},
            ]
        )
    }
    assert scoped["AI 自动回复消息"] == 1  # 仅企微
    assert scoped["AI 评论回复"] == 1  # 仅公域 comment_reply，排除 wechat


def test_core_metrics_by_agent_breakdown() -> None:
    """by_agent：白名单全列（含 0）；合计等于 value；不跨域."""
    rows = [
        {"profile_id": "douyin", "op_type": "inbound_reply"},
        {"profile_id": "qiyeweixin", "op_type": "inbound_reply"},
        {"profile_id": "qiyeweixin", "op_type": "inbound_reply"},
        {"profile_id": "wechat", "op_type": "inbound_reply"},
        {"profile_id": "boss", "op_type": "comment_reply"},  # 公域指标，不应进自动回复
    ]
    items = {c["label"]: c for c in _core_metrics(rows)}
    auto = items["AI 自动回复消息"]
    assert auto["value"] == 3
    by = {a["profile_id"]: a for a in auto["by_agent"]}
    assert set(by) == {"wechat", "qiyeweixin", "boss"}
    assert by["wechat"]["value"] == 1
    assert by["qiyeweixin"]["value"] == 2
    assert by["boss"]["value"] == 0
    assert by["wechat"]["name"] == "个微"
    assert sum(a["value"] for a in auto["by_agent"]) == auto["value"]

    pub = items["评论抓取总数"]
    assert pub["value"] == 0
    assert [a["profile_id"] for a in pub["by_agent"]] == [
        "douyin",
        "xiaohongshu",
        "shipinhao",
    ]
    assert all(a["value"] == 0 for a in pub["by_agent"])

    wx = items["微信主动加好友"]
    assert [a["profile_id"] for a in wx["by_agent"]] == ["wechat"]
    assert wx["by_agent"][0]["value"] == 0


def test_core_channel_scopes_exclude_cross_domain() -> None:
    """公域指标不含私域；微信加好友不含企微；主动推送不含公域."""
    rows = [
        {"profile_id": "wechat", "op_type": "comment_collect"},
        {"profile_id": "douyin", "op_type": "comment_collect"},
        {"profile_id": "wechat", "op_type": "add_friends"},
        {"profile_id": "qiyeweixin", "op_type": "add_friends"},
        {"profile_id": "qiyeweixin", "op_type": "add_contacts"},
        {"profile_id": "douyin", "op_type": "dm"},
        {"profile_id": "wechat", "op_type": "dm"},
        {"profile_id": "douyin", "op_type": "scheduled_msg"},
        {"profile_id": "boss", "op_type": "scheduled_msg"},
        {"profile_id": "wechat", "op_type": "first_comment"},
        {"profile_id": "xiaohongshu", "op_type": "first_comment"},
    ]
    core = {c["label"]: c["value"] for c in _core_metrics(rows)}
    assert core["评论抓取总数"] == 1  # 仅 douyin
    assert core["主动评论发送"] == 1  # 仅 xiaohongshu
    assert core["自动私信发送"] == 1  # 仅 douyin
    assert core["微信主动加好友"] == 1  # 仅 wechat
    assert core["企业微信主动加好友"] == 1  # 仅 qiyeweixin add_contacts
    assert core["AI 主动消息推送"] == 1  # 仅 boss（douyin 公域排除）


def test_core_rule_by_label_and_list_worklogs_align() -> None:
    """下钻 list_worklogs(op_types+profiles+since_days) 与核心计数同口径."""
    append_worklog(
        profile_id="wechat",
        op_type="add_friends",
        exec_status="成功",
        op_object="真实加好友",
    )
    append_worklog(
        profile_id="wechat",
        op_type="微信主动加好友",
        exec_status="成功",
        op_object="demo加好友",
    )
    append_worklog(
        profile_id="qiyeweixin",
        op_type="add_friends",
        exec_status="成功",
        op_object="企微误标不应计入微信",
    )
    rule = core_rule_by_label("微信主动加好友")
    assert rule is not None
    _label, keys, profiles = rule
    items = list_worklogs(
        profile_ids=sorted(profiles),
        op_types=list(keys),
        since_days=7,
        limit=500,
    )
    core = {c["label"]: c["value"] for c in stats_summary(range_days=7)["core"]}
    # 本测追加至少 2 条 wechat；与 summary 同过滤后条数应 ≥2 且不含企微
    assert all(r["profile_id"] == "wechat" for r in items)
    assert all(r["op_type"] in keys for r in items)
    assert core["微信主动加好友"] >= 2
    assert len(items) >= 2
