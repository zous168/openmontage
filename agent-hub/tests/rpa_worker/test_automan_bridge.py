"""automan_bridge 单测（LT-032.02.01）.

覆盖：task_type→api_slug（hub 业务约定）、按 slug 寻址、per-type 入参契约、缺口 no_workflow。
slug 由 hub 定，automan 按 slug 内部解析 workflow_id（hub 不持有 workflow_id）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.mxai.rpa_worker import automan_bridge as ab


def _task(task_type, payload, *, task_id="t-1", profile_id="wechat", operator="系统自动"):
    return SimpleNamespace(
        task_id=task_id, task_type=task_type, profile_id=profile_id,
        operator=operator, payload=payload, name="t", priority=1,
    )


def test_inbound_reply_uses_hub_reply_text():
    frame = ab.to_execute(_task("inbound_reply", {"sender": "wxid_demo", "hub_reply": {"text": "您好"}}))
    assert frame["type"] == ab.MSG_WORKFLOW_EXECUTE
    assert frame["slug"] == "weixin_reply"
    # msg=兼容旧工作流；msgs=多气泡连发（空行拆分后的列表）
    assert frame["inputs"] == {"inputid": "wxid_demo", "msg": "您好", "msgs": ["您好"]}


def test_dm_maps_recipient_message():
    frame = ab.to_execute(_task("dm", {"recipient": "u1", "message": "hi"}))
    assert frame["slug"] == "weixin_sendmsg"
    assert frame["inputs"] == {"inputid": "u1", "msg": "hi"}


def test_add_friends_maps_contact_applymsg():
    frame = ab.to_execute(_task("add_friends", {"contacts": ["c1", "c2"], "template": "你好"}))
    assert frame["slug"] == "weixin_addfriends"
    assert frame["inputs"] == {"inputid": "c1", "applymsg": "你好"}


def test_add_friends_greeting_maps_to_applymsg():
    # greeting（前端申请语）优先于 template → applymsg
    frame = ab.to_execute(_task("add_friends", {"contacts": ["c1"], "greeting": "你好加个好友"}))
    assert frame["inputs"] == {"inputid": "c1", "applymsg": "你好加个好友"}


def test_qiwei_add_friends_slug():
    frame = ab.to_execute(_task("add_friends", {"contacts": ["c1"], "greeting": "你好"}, profile_id="qiyeweixin"))
    assert frame["slug"] == "qiwei_addfriends"


def test_qiwei_add_contacts_slug_and_inputs():
    frame = ab.to_execute(
        _task(
            "add_contacts",
            {"contacts": ["qw1"], "contact_id": "qw1", "greeting": "你好"},
            profile_id="qiyeweixin",
        )
    )
    assert frame["slug"] == "qiwei_addfriends"
    assert frame["inputs"] == {"inputid": "qw1", "applymsg": "你好"}


def test_gap_task_type_sends_fallback_slug():
    # 纯 B：hub 不本地短路，动作无映射时回退用 task_type 拼前缀发给 automan（automan 告警+failed）
    for tt in ("boss_search", "send_file"):
        frame = ab.to_execute(_task(tt, {}))
        assert frame["type"] == ab.MSG_WORKFLOW_EXECUTE
        assert frame["slug"] == f"weixin_{tt}"  # 前缀 wechat→weixin，动作回退=task_type


def test_douyin_public_slugs():
    assert ab.douyin_public_slugs() == ab.DOUYIN_PUBLIC_SLUGS
    assert ab.slug_for("comment_collect", "douyin") == "douyin_comment_collect"
    assert ab.slug_for("comment_reply", "douyin") == "douyin_comment_reply"
    assert ab.slug_for("first_comment", "douyin") == "douyin_first_comment"
    assert ab.slug_for("dm", "douyin") == "douyin_sendmsg"


def test_douyin_comment_collect_inputs():
    frame = ab.to_execute(
        _task(
            "comment_collect",
            {
                "search_keywords": ["智能客服", "报价"],
                "match_keywords": ["多少钱"],
                "max_videos_per_run": 3,
                "max_customers_per_run": 8,
            },
            profile_id="douyin",
        )
    )
    assert frame["slug"] == "douyin_comment_collect"
    assert frame["inputs"] == {
        "search_keywords": "智能客服,报价",
        "match_keywords": "多少钱",
        "max_videos": 3,
        "max_customers": 8,
    }


def test_douyin_comment_reply_inputs():
    frame = ab.to_execute(
        _task(
            "comment_reply",
            {
                "search_keywords": ["智能客服", "报价"],
                "author_name": "我的抖音号",
                "max_videos_per_run": 4,
                "max_comments_per_run": 12,
            },
            profile_id="douyin",
        )
    )
    assert frame["slug"] == "douyin_comment_reply"
    assert frame["inputs"] == {
        "key_words": "智能客服,报价",
        "max_videos": 4,
        "max_comments": 12,
    }
    assert "author_name" not in frame["inputs"]


def test_douyin_dm_inputs():
    frame = ab.to_execute(
        _task("dm", {"recipient": "dy_uid", "message": "你好"}, profile_id="douyin")
    )
    assert frame["slug"] == "douyin_sendmsg"
    assert frame["inputs"] == {"inputid": "dy_uid", "msg": "你好"}


def test_douyin_first_comment_key_words():
    frame = ab.to_execute(
        _task("first_comment", {"benchmarks": ["@bench_a"]}, profile_id="douyin")
    )
    assert frame["slug"] == "douyin_first_comment"
    assert frame["inputs"] == {"key_words": "@bench_a"}


def test_from_result_normalizes_outputs():
    out = ab.from_result("dm", {"sent": True})
    assert out["sent"] is True
    assert out["mode"] == "automan"
    assert out["send_status"] == "sent"
    assert out["send"]["sent"] is True


@pytest.mark.parametrize(
    ("outputs", "workflow_status", "expected"),
    [
        ({"send_status": "not_sent"}, "succeeded", "not_sent"),
        ({"sent": True}, "failed", "sent"),
        ({}, "completed", "sent"),
        ({}, "failed", "unknown"),
    ],
)
def test_scheduled_msg_send_status_normalization(outputs, workflow_status, expected):
    out = ab.from_result(
        "scheduled_msg",
        outputs,
        workflow_status=workflow_status,
    )
    assert out["send_status"] == expected


@pytest.mark.parametrize(
    ("outputs", "workflow_status", "expected"),
    [
        ({"send_status": "not_sent"}, "succeeded", "not_sent"),
        ({}, "succeeded", "sent"),
        ({}, "failed", "unknown"),
    ],
)
def test_dm_send_status_normalization(outputs, workflow_status, expected):
    out = ab.from_result("dm", outputs, workflow_status=workflow_status)
    assert out["send_status"] == expected
    if expected == "sent":
        assert out.get("send", {}).get("sent") is True


def test_request_id_defaults_to_task_id():
    frame = ab.to_execute(_task("dm", {"recipient": "u", "message": "m"}, task_id="tsk_9"))
    assert frame["request_id"] == "tsk_9"


def test_slug_for_known_and_fallback():
    # slug = {渠道前缀}_{动作}
    assert ab.slug_for("scheduled_msg", "wechat") == "weixin_sendmsg"
    assert ab.slug_for("follow_up", "wechat") == "weixin_sendmsg"
    assert ab.slug_for("moments_publish", "wechat") == "weixin_moments_post"
    assert ab.slug_for("add_friends", "qiyeweixin") == "qiwei_addfriends"
    assert ab.slug_for("add_contacts", "qiyeweixin") == "qiwei_addfriends"
    # CR-146 Boss 三 slug
    assert ab.slug_for("greet", "boss") == "boss_greet"
    assert ab.slug_for("inbound_reply", "boss") == "boss_reply"
    assert ab.slug_for("inbound_listen", "boss") == "boss_listen"
    assert ab.slug_for("dm", "boss") == "boss_sendmsg"
    # 动作无映射 → 回退用 task_type 拼前缀（automan 侧再判）
    assert ab.slug_for("invite", "wechat") == "weixin_invite"
    # 渠道无前缀映射 → 回退用 profile_id 原值拼接
    assert ab.slug_for("dm", "unknownch") == "unknownch_sendmsg"


def test_boss_greet_inputs():
    frame = ab.to_execute(
        _task(
            "greet",
            {"candidates": ["c1"], "template": "您好", "greet_count": 20, "greeting_templates": ["您好"]},
            profile_id="boss",
        )
    )
    assert frame["slug"] == "boss_greet"
    assert frame["inputs"]["inputid"] == "c1"
    assert frame["inputs"]["msg"] == "您好"
    assert frame["inputs"]["new_number"] == 20


def test_boss_greet_inputs_cr148_keys():
    frame = ab.to_execute(
        _task(
            "greet",
            {
                "candidates": ["c1"],
                "template": "您好",
                "new_number": 15,
                "zhiwei": "Java工程师",
                "zhize": "3年经验",
            },
            profile_id="boss",
        )
    )
    assert frame["inputs"] == {
        "inputid": "c1",
        "msg": "您好",
        "new_number": 15,
        "zhiwei": "Java工程师",
        "zhize": "3年经验",
    }


def test_boss_channel_rpa_task_types():
    types = ab.channel_rpa_task_types("boss")
    assert {"greet", "inbound_reply", "dm", "follow_up"}.issubset(types)


def test_qiyeweixin_channel_includes_scheduled_msg():
    assert "scheduled_msg" in ab.channel_rpa_task_types("qiyeweixin")


# 可选工具：HTTP 拉取模式下 slug→workflow_id（保留备用）
def test_build_slug_index_optional_tool():
    idx = ab.build_slug_index([{"id": "w1", "api_slug": "sendmsg"}, {"id": "w2"}])
    assert idx == {"sendmsg": "w1"}


def test_monitor_slugs_for_channels_dedupes_inbound_reply():
    slugs = ab.monitor_slugs_for_channels(["wechat", "wechat", "boss"])
    assert slugs == ["weixin_listen", "boss_listen"]


def test_monitor_slugs_for_channel_subset_task_types():
    slugs = ab.monitor_slugs_for_channel("wechat", ["inbound_reply"])
    assert slugs == ["weixin_listen"]


def test_resolve_monitor_slugs_single_slug():
    assert ab.resolve_monitor_slugs(slugs=["weixin_listen"]) == ["weixin_listen"]


def test_resolve_monitor_slugs_channel_all():
    assert ab.resolve_monitor_slugs(channels=["wechat"]) == ["weixin_listen"]


def test_resolve_monitor_slugs_global_all():
    slugs = ab.resolve_monitor_slugs()
    assert "weixin_listen" in slugs
    assert "boss_listen" in slugs


def test_resolve_monitor_slugs_scope_all():
    assert set(ab.resolve_monitor_slugs(scope="all")) == set(ab.all_monitor_slugs())


def test_resolve_monitor_slugs_task_types_only():
    slugs = set(ab.resolve_monitor_slugs(task_types=["inbound_reply"]))
    assert slugs == {"weixin_listen", "qiwei_listen", "boss_listen"}


def test_resolve_monitor_slugs_explicit_empty():
    assert ab.resolve_monitor_slugs(slugs=[], slugs_explicit=True) == []


def test_list_monitor_catalog():
    items = ab.list_monitor_catalog(["wechat"])
    assert items == [{"channel": "wechat", "task_type": "inbound_reply", "slug": "weixin_listen"}]


def test_listen_slug_for_channel():
    assert ab.listen_slug_for_channel("qiyeweixin") == "qiwei_listen"
    assert ab.listen_slug_for_channel("douyin") is None


def test_monitor_listen_slugs_for_channels():
    assert ab.monitor_listen_slugs_for_channels(["wechat", "qiyeweixin"]) == [
        "weixin_listen",
        "qiwei_listen",
    ]


# ── CR-164：HTTP health 离线→在线边沿 ─────────────────────────────────


def test_probe_http_health_offline_to_online_notifies_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """health false→true 只触发一次上线回调；持续在线不再冲。"""
    ab.reset_http_health_probe_state()
    calls: list[int] = []
    monkeypatch.setattr(ab, "_notify_http_became_online", lambda: calls.append(1))

    codes = [503, 200, 200]

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):  # noqa: ARG002
            return SimpleNamespace(status_code=codes.pop(0))

    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    url = "http://127.0.0.1:18123"
    assert ab.probe_http_health(url, ttl=0.0) is False
    assert calls == []
    assert ab.probe_http_health(url, ttl=0.0) is True
    assert calls == [1]
    assert ab.probe_http_health(url, ttl=0.0) is True
    assert calls == [1]


def test_probe_http_health_unknown_to_online_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次探活即为在线（未知→在线）也冲一次，便于 hub 重启后清积压。"""
    ab.reset_http_health_probe_state()
    calls: list[int] = []
    monkeypatch.setattr(ab, "_notify_http_became_online", lambda: calls.append(1))

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):  # noqa: ARG002
            return SimpleNamespace(status_code=200)

    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    assert ab.probe_http_health("http://127.0.0.1:18123", ttl=0.0) is True
    assert calls == [1]


def test_notify_http_became_online_calls_queue_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """上线回调落到 QueueManager.notify_worker_connected（与 WS register 对称）."""
    notified: list[str] = []

    class _Q:
        def notify_worker_connected(self) -> None:
            notified.append("ok")

    class _QM:
        @staticmethod
        def get():
            return _Q()

    import plugins.mxai.orchestrator.queue_manager as qm_mod

    monkeypatch.setattr(qm_mod, "QueueManager", _QM)
    ab._notify_http_became_online()
    assert notified == ["ok"]
