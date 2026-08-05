"""开发调试 REST 契约验收（CR-123 · §2.9b · LT-035/LT-036）.

覆盖：GET /dev/automan/agents 各渠道 ready（仅个微 ready）；POST /dev/automan/exec **两种调用方式**
（``mode``，FR-DEV-08 · CR-124）——
- ``enqueue``（默认）：入队（status=queued）、task 在队列、operator=debug、bypass_work_armed（未开工不返 409）；
- ``direct``：同步直调 bridge（mock stub）→ status=done + result、**不入队列**、**零 WorkLog**；
两种 mode 的 ``no_workflow`` 渠道均立即显式失败、不伪成功；(task_type,profile_id)→slug 渠道前缀化映射
（wechat+add_friends→weixin_addfriends）；raw 模式直发 inputs。另含全局 RPA 单锁
（``rpa_exclusive``/``acquire/release_rpa_slot``）互斥单测。
``MXAI_MOCK=1`` 由 mxai_env fixture 注入；bridge.execute_via_worker 由 conftest stub 为同步返回。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.orchestrator.queue_manager import WorkNotStartedError
from plugins.mxai.worklog.service import list_worklogs

_BASE = "/api/plugins/mxai/dev"


def _exec(client: TestClient, **body) -> dict:
    res = client.post(f"{_BASE}/automan/exec", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_agents_readiness_only_wechat(mxai_client: TestClient) -> None:
    res = mxai_client.get(f"{_BASE}/automan/agents")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 6
    by_pid = {it["profile_id"]: it for it in body["items"]}
    assert set(by_pid) == {"wechat", "qiyeweixin", "douyin", "xiaohongshu", "shipinhao", "boss"}
    # 仅个人微信 automan 已挂 api_slug → ready=true
    assert by_pid["wechat"]["ready"] is True
    assert "dm" in by_pid["wechat"]["workflows"]
    assert "add_friends" in by_pid["wechat"]["workflows"]
    # 抖音 hub 已定义 slug，automan 未挂 → ready=false、workflows 非空
    # CR-169：抖音多一个 video_comment（小红书/视频号本期不含）
    assert by_pid["douyin"]["ready"] is False
    assert set(by_pid["douyin"]["workflows"]) == {
        "comment_collect", "comment_reply", "first_comment", "dm", "video_comment",
    }
    for pid in ("qiyeweixin", "boss", "xiaohongshu", "shipinhao"):
        if pid in ("xiaohongshu", "shipinhao"):
            assert by_pid[pid]["ready"] is False
            assert set(by_pid[pid]["workflows"]) == {
                "comment_collect", "comment_reply", "first_comment", "dm",
            }
        else:
            assert by_pid[pid]["ready"] is False
        assert "name" in by_pid[pid]


# ── 默认调用方式 = 入队（enqueue）──────────────────────────────────────────────
def test_exec_default_mode_enqueues_as_debug(mxai_client: TestClient) -> None:
    """不带 mode → 默认 enqueue：返回 queued，task 在队列、operator=debug。"""
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="dm",
        payload={"recipient": "wxid_xxx", "message": "调试消息"},
    )
    assert body["workflow"] == "weixin_sendmsg"
    assert body["no_workflow"] is False
    assert body["status"] == "queued"
    assert body["task_id"].startswith("tsk_")
    task = get_queue().get_task(body["task_id"])
    assert task is not None
    assert task.operator == "debug"
    assert task.task_type == "dm"


def test_exec_add_friends_maps_addfriend(mxai_client: TestClient) -> None:
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="add_friends",
        payload={"contact": "wxid_xxx", "greeting": "你好"},
    )
    assert body["workflow"] == "weixin_addfriends"
    assert body["no_workflow"] is False
    assert body["status"] == "queued"


def test_exec_enqueue_bypasses_work_armed_gate(mxai_client: TestClient) -> None:
    """未开工状态下 enqueue 调用经 bypass_work_armed 仍入队（不返 409）。"""
    q = get_queue()
    q.disarm_work()
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="dm",
        mode="enqueue",
        payload={"recipient": "wxid_xxx", "message": "未开工也能调试"},
    )
    assert body["status"] == "queued"
    assert get_queue().get_task(body["task_id"]) is not None


# ── 直接调用（direct）：同步、不入队列、零落痕 ───────────────────────────────────
def test_exec_direct_mode_synchronous(mxai_client: TestClient) -> None:
    """mode=direct → 同步执行（mock bridge stub）→ done + result；不入队列。"""
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="dm",
        mode="direct",
        payload={"recipient": "wxid_xxx", "message": "直接调用"},
    )
    assert body["workflow"] == "weixin_sendmsg"
    assert body["no_workflow"] is False
    assert body["status"] == "done"
    assert "result" in body
    # 直接调用不入队列
    assert get_queue().get_task(body["task_id"]) is None


def test_exec_direct_mode_zero_worklog(mxai_client: TestClient) -> None:
    """CR-124 关键：直接调用**零 WorkLog**（与入队调用写痕、AI 调试零落痕一致）。"""
    before = len(list_worklogs(profile_id="wechat", limit=1000))
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="dm",
        mode="direct",
        payload={"recipient": "wxid_log", "message": "零落痕"},
    )
    assert body["status"] in ("done", "failed")
    after = len(list_worklogs(profile_id="wechat", limit=1000))
    assert after == before, "直接调用不应写 WorkLog（零落痕）"


# ── no_workflow 诚实（hub 未定义 slug）──────────────────────────────────────────
def test_exec_boss_greet_has_slug(mxai_client: TestClient) -> None:
    """Boss 打招呼：hub 已定义 boss_greet → no_workflow:false、正常入队。"""
    body = _exec(
        mxai_client,
        profile_id="boss",
        task_type="greet",
        payload={"candidates": ["c1"], "template": "你好"},
    )
    assert body["workflow"] == "boss_greet"
    assert body["no_workflow"] is False
    assert body["status"] == "queued"
    task = get_queue().get_task(body["task_id"])
    assert task is not None
    assert task.task_type == "greet"


def test_exec_no_workflow_unknown_task_on_boss(mxai_client: TestClient) -> None:
    """Boss 渠道 hub 未定义 task_type → no_workflow:true、failed。"""
    for mode in ("enqueue", "direct"):
        body = _exec(
            mxai_client,
            profile_id="boss",
            task_type="send_file",
            mode=mode,
            payload={},
        )
        assert body["no_workflow"] is True, mode
        assert body["status"] == "failed", mode
        assert "error" in body
        assert get_queue().get_task(body["task_id"]) is None


def test_exec_douyin_dm_has_slug(mxai_client: TestClient) -> None:
    """抖音发私信：hub 已定义 douyin_sendmsg → no_workflow:false、正常入队。"""
    body = _exec(
        mxai_client,
        profile_id="douyin",
        task_type="dm",
        payload={"recipient": "douyin_uid", "message": "抖音调试"},
    )
    assert body["workflow"] == "douyin_sendmsg"
    assert body["no_workflow"] is False
    assert body["status"] == "queued"
    task = get_queue().get_task(body["task_id"])
    assert task is not None
    assert task.task_type == "dm"


def test_exec_raw_inputs_passthrough(mxai_client: TestClient) -> None:
    """raw 模式直发 inputs（默认 enqueue）：workflow=sendmsg、入队。"""
    body = _exec(
        mxai_client,
        profile_id="wechat",
        task_type="dm",
        raw=True,
        inputs={"inputid": "wxid_raw", "msg": "原始调用测试"},
    )
    assert body["workflow"] == "weixin_sendmsg"
    assert body["no_workflow"] is False
    assert body["status"] == "queued"


def test_exec_unknown_agent_404(mxai_client: TestClient) -> None:
    res = mxai_client.post(
        f"{_BASE}/automan/exec",
        json={"profile_id": "nope", "task_type": "dm"},
    )
    assert res.status_code == 404


def test_exec_non_rpa_task_type_rejected(mxai_client: TestClient) -> None:
    res = mxai_client.post(
        f"{_BASE}/automan/exec",
        json={"profile_id": "wechat", "task_type": "report"},
    )
    assert res.status_code == 400


# ── 全局 RPA 单锁：执行级互斥量（队列 drain 与 dev direct 竞争同一把 · CR-124 / 16 §12.6）──
def test_rpa_exclusive_mutex_unit(mxai_env: Path) -> None:
    """acquire/release_rpa_slot 互斥：占用时第二持有者超时失败；释放后可再获取。"""
    del mxai_env
    q = get_queue()
    assert q.acquire_rpa_slot("holder-1", timeout=1.0) is True
    # 锁被占 → 第二持有者短超时获取失败
    assert q.acquire_rpa_slot("holder-2", timeout=0.2) is False
    q.release_rpa_slot("holder-1")
    # 释放后可再获取
    assert q.acquire_rpa_slot("holder-2", timeout=1.0) is True
    q.release_rpa_slot("holder-2")


def test_rpa_exclusive_context_releases_on_error(mxai_env: Path) -> None:
    """rpa_exclusive 上下文异常退出也释放单锁（finally）；忙时抛 TimeoutError。"""
    del mxai_env
    q = get_queue()
    with pytest.raises(RuntimeError):
        with q.rpa_exclusive("ctx-1", timeout=1.0):
            raise RuntimeError("boom")
    # 异常后已释放 → 可再获取
    assert q.acquire_rpa_slot("ctx-2", timeout=1.0) is True
    q.release_rpa_slot("ctx-2")
    # 占用时 rpa_exclusive 忙 → TimeoutError
    assert q.acquire_rpa_slot("hold", timeout=1.0) is True
    with pytest.raises(TimeoutError):
        with q.rpa_exclusive("busy", timeout=0.2):
            pass  # pragma: no cover
    q.release_rpa_slot("hold")


def test_enqueue_bypass_work_armed_unit(mxai_env: Path) -> None:
    """单测：enqueue(bypass_work_armed=True) 未开工不抛错；默认 False 抛错（零回归）。"""
    del mxai_env
    q = get_queue()
    q.disarm_work()
    q.set_global_pause(True)
    # 默认 False → 抛
    with pytest.raises(WorkNotStartedError):
        q.enqueue(profile_id="wechat", name="x", task_type="dm", skip_risk=True)
    # bypass → 入队成功
    task = q.enqueue(
        profile_id="wechat",
        name="bypass",
        task_type="dm",
        skip_risk=True,
        bypass_work_armed=True,
    )
    assert task is not None
    assert task.task_id.startswith("tsk_")
