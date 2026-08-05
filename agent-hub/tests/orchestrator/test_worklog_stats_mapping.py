"""CR-77 / doc 13 §6.3b：业务流程 WorkLog op_type 与 stats/goals 对账."""

from __future__ import annotations

import time
from typing import Any

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.orchestrator.models import Task, TaskStatus
from plugins.mxai.orchestrator.queue_manager import QueueManager, _greet_task_peer
from plugins.mxai.reports.service import generate_report
from plugins.mxai.stats.service import stats_summary
from plugins.mxai.rpa_worker.bridge import reset_rpa_worker_bridge
from plugins.mxai.worklog.service import append_worklog, list_worklogs


def _unlock(client: TestClient, *agents: str) -> None:
    client.post("/api/plugins/mxai/queue/resume")
    for agent in agents:
        client.post(f"/api/plugins/mxai/run/agents/{agent}/start")


def _core_value(summary: dict[str, Any], label: str) -> int:
    for item in summary.get("core") or []:
        if item.get("label") == label:
            return int(item.get("value") or 0)
    return 0


def _run_task(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    profile_id: str,
    task_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    del mxai_env
    reset_rpa_worker_bridge()

    # v4.0（LT-032）：经 worker 完成（取代旧 fallback）。挂连接桩，execute_via_worker 返回预置 result。
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    bridge = get_rpa_worker_bridge()
    monkeypatch.setattr(bridge, "is_connected", lambda: True)
    monkeypatch.setattr(bridge, "execute_via_worker", lambda task, timeout=600.0: result)

    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled(profile_id, True)
    q.enqueue(
        profile_id=profile_id,
        name=f"test-{task_type}",
        task_type=task_type,
        payload=payload,
        skip_risk=True,
    )
    time.sleep(0.3)


def test_cr77_comment_collect_worklog_and_stats_kpi(
    mxai_client: TestClient,
    mxai_env: Path,
) -> None:
    del mxai_env
    before = _core_value(mxai_client.get("/api/plugins/mxai/stats/summary").json(), "评论抓取总数")
    _unlock(mxai_client, "douyin")
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"keywords": ["CR77"]},
    )
    assert resp.status_code == 200
    time.sleep(0.5)
    logs = list_worklogs(profile_id="douyin", limit=10)
    assert any(
        log.get("op_type") == "comment_collect" and log.get("exec_status") == "成功"
        for log in logs
    )
    after = _core_value(mxai_client.get("/api/plugins/mxai/stats/summary").json(), "评论抓取总数")
    assert after >= before + 1


def test_cr77_dm_worklog_op_type_and_qa(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="douyin",
        task_type="dm",
        payload={"recipient": "lead_1", "message": "想了解产品"},
        result={
            "reply": {"text": "感谢咨询，稍后联系您。", "source": "llm"},
            "send": {"sent": True},
        },
    )
    logs = list_worklogs(profile_id="douyin", limit=5)
    assert logs
    assert logs[0].get("op_type") == "dm"
    obj = logs[0].get("op_object") or ""
    assert "lead_1" in obj
    assert "问:" in obj
    assert "答:" in obj


def test_cr77_inbound_reply_goals_today(
    mxai_client: TestClient,
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/goals",
        json={"goals": [{"metric": "消息回复", "daily_target": 10}]},
    )
    before = mxai_client.get("/api/plugins/mxai/agents/wechat/goals/today").json()
    done_before = next(
        (i["done"] for i in before["items"] if i["metric"] == "消息回复"),
        0,
    )
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="wechat",
        task_type="inbound_reply",
        payload={"sender": "客户B", "message": "在吗", "message_id": "cr77-m1"},
        result={
            "reply": {"text": "您好，请问有什么可以帮您？", "source": "faq"},
            "send": {"sent": True},
        },
    )
    logs = list_worklogs(profile_id="wechat", limit=5)
    assert any(log.get("op_type") == "inbound_reply" for log in logs)
    after = mxai_client.get("/api/plugins/mxai/agents/wechat/goals/today").json()
    done_after = next(
        (i["done"] for i in after["items"] if i["metric"] == "消息回复"),
        0,
    )
    assert done_after >= done_before + 1


def test_cr77_first_comment_worklog(
    mxai_client: TestClient,
    mxai_env: Path,
) -> None:
    del mxai_env
    _unlock(mxai_client, "douyin")
    mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/first-comment",
        json={"scripts": ["首评话术"], "benchmarks": ["@demo"]},
    )
    time.sleep(0.5)
    logs = list_worklogs(profile_id="douyin", limit=10)
    assert any(
        log.get("op_type") == "first_comment" and log.get("exec_status") == "成功"
        for log in logs
    )


def test_cr77_scheduled_msg_worklog(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="wechat",
        task_type="scheduled_msg",
        payload={"recipient": "vip_1", "message": "活动提醒"},
        result={"send": {"message": "活动提醒", "sent": True}},
    )
    logs = list_worklogs(profile_id="wechat", limit=5)
    assert logs[0]["op_type"] == "scheduled_msg"
    assert "vip_1" in (logs[0].get("op_object") or "")
    assert "活动提醒" in (logs[0].get("op_object") or "")


def test_cr77_add_friends_worklog(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="wechat",
        task_type="add_friends",
        payload={"phones": ["13800001111"]},
        result={"added": 1},
    )
    logs = list_worklogs(profile_id="wechat", limit=5)
    assert logs[0]["op_type"] == "add_friends"
    assert logs[0]["exec_status"] == "成功"


def test_cr77_boss_greet_worklog(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boss greet 任务终态不写台账；台账由 greet-register 负责（防双写）."""
    before = list_worklogs(profile_id="boss", limit=50)
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="boss",
        task_type="greet",
        payload={"candidate": "张三", "message": "您好"},
        result={"reply": {"text": "您好，欢迎投递"}, "send": {"sent": True}},
    )
    after = list_worklogs(profile_id="boss", limit=50)
    assert len(after) == len(before)


def test_greet_task_peer_empty_when_batch_by_position() -> None:
    """生产环境 greet 入队：candidates=[] + zhiwei，无具体候选."""
    task = Task(
        task_id="t1",
        profile_id="boss",
        name="打招呼",
        task_type="greet",
        status=TaskStatus.QUEUED,
        payload={"candidates": [], "zhiwei": "新媒体销售专员", "new_number": 1},
    )
    assert _greet_task_peer(task) == ""


def test_boss_greet_batch_skips_task_completion_worklog(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按职位批量打招呼：候选由 greet-register 留痕，任务完成不得再写伪台账行."""
    before = list_worklogs(profile_id="boss", limit=50)
    _run_task(
        mxai_env,
        monkeypatch,
        profile_id="boss",
        task_type="greet",
        payload={
            "candidates": [],
            "zhiwei": "新媒体销售专员",
            "new_number": 1,
            "greeting_templates": ["您好"],
            "template": "您好",
        },
        result={"send": {"sent": True}},
    )
    after = list_worklogs(profile_id="boss", limit=50)
    assert len(after) == len(before)


def test_inbound_reply_failure_worklog_has_op_object(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """listen signal 任务失败时台账 op_object 不得为空（至少「监听触发」）."""
    del mxai_env
    reset_rpa_worker_bridge()
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    bridge = get_rpa_worker_bridge()
    monkeypatch.setattr(bridge, "is_connected", lambda: True)

    def _fail(task, timeout=600.0):
        raise RuntimeError("SCRCPY_UNAVAILABLE: mock")

    monkeypatch.setattr(bridge, "execute_via_worker", _fail)
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("boss", True)
    before = {row["log_id"] for row in list_worklogs(profile_id="boss", limit=100)}
    q.enqueue(
        profile_id="boss",
        name="监听回复",
        task_type="inbound_reply",
        payload={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": "sig-fail-1",
            "source": "automan_listen",
        },
        skip_risk=True,
    )
    time.sleep(0.4)
    after = list_worklogs(profile_id="boss", limit=20)
    fresh = [row for row in after if row["log_id"] not in before]
    assert fresh, "expected failure worklog"
    row = fresh[0]
    assert row["op_type"] == "inbound_reply"
    assert row["exec_status"] == "失败"
    assert str(row.get("op_object") or "").strip() == "监听触发"


def test_cr77_failed_task_not_counted_in_goals(
    mxai_client: TestClient,
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del mxai_env
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/goals",
        json={"goals": [{"metric": "私信触达", "daily_target": 5}]},
    )
    before = mxai_client.get("/api/plugins/mxai/agents/douyin/goals/today").json()
    done_before = next(
        (i["done"] for i in before["items"] if i["metric"] == "私信触达"),
        0,
    )

    def fail_worker(task, timeout=600.0):
        raise RuntimeError("mock fail")

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    _b = get_rpa_worker_bridge()
    monkeypatch.setattr(_b, "is_connected", lambda: True)
    monkeypatch.setattr(_b, "execute_via_worker", fail_worker)
    q = get_queue()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    q.enqueue(
        profile_id="douyin",
        name="fail-dm",
        task_type="dm",
        payload={"recipient": "x", "message": "y"},
        skip_risk=True,
    )
    time.sleep(0.3)
    logs = list_worklogs(profile_id="douyin", limit=3)
    assert logs[0]["exec_status"] == "失败"
    after = mxai_client.get("/api/plugins/mxai/agents/douyin/goals/today").json()
    done_after = next(
        (i["done"] for i in after["items"] if i["metric"] == "私信触达"),
        0,
    )
    assert done_after == done_before


def test_cr77_report_snapshot_matches_worklog(
    mxai_env: Path,
) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="comment_collect",
        exec_status="成功",
        op_object="kw",
        data_dir=mxai_env,
    )
    append_worklog(
        profile_id="douyin",
        op_type="comment_collect",
        exec_status="失败",
        op_object="kw2",
        data_dir=mxai_env,
    )
    report = generate_report("daily", profile_id="douyin", data_dir=mxai_env)
    logs = list_worklogs(profile_id="douyin", limit=50, data_dir=mxai_env)
    today_logs = logs  # generate_report already filters by period
    success = sum(1 for log in today_logs if log.get("exec_status") == "成功")
    assert report["totals"]["success"] == success
    assert report["totals"]["entries"] == len(today_logs)


def test_cr77_stats_summary_hand_computed(mxai_env: Path) -> None:
    del mxai_env
    append_worklog(
        profile_id="wechat",
        op_type="inbound_reply",
        exec_status="成功",
    )
    summary = stats_summary(range_days=7)
    consult = summary.get("consult_total") or 0
    assert consult >= 1
    ai_kpi = _core_value(summary, "AI 自动回复消息")
    assert ai_kpi >= 1


def test_cr77_chat_completions_no_worklog(mxai_client: TestClient) -> None:
    before = len(list_worklogs(limit=200))
    mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "你好", "agent": "main"},
    )
    after = len(list_worklogs(limit=200))
    assert after == before
