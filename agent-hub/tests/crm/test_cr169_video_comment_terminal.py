"""CR-169 · 终态回写 / bridge 映射 / WorkLog 字段。"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.crm.funnel import apply_funnel_from_task
from plugins.mxai.crm.lead_service import (
    VIDEO_COMMENT_NO_VIDEO,
    VIDEO_COMMENT_NOT_SENT,
    VIDEO_COMMENT_SENT,
    get_lead,
    insert_comment_lead,
    list_lead_ids_pending_video_comment,
)
from plugins.mxai.rpa_worker.automan_bridge import _inputs_for, from_result, slug_for


@pytest.fixture
def vc_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """全局单例（ConfigManager/QueueManager）跨用例残留会让整包跑与单跑结果不同，逐例重置。"""
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.orchestrator.queue_manager import QueueManager

    data_dir = tmp_path / "hub"
    (data_dir / "profiles" / "douyin").mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path", lambda: data_dir
    )
    ConfigManager.reset()
    QueueManager.reset()
    return data_dir


def _seed(env: Path, douyin_id: str = "dy_t") -> str:
    r = insert_comment_lead(
        profile_id="douyin",
        nickname="客户",
        douyin_id=douyin_id,
        comment="c",
        intent="高",
        data_dir=env,
    )
    return str(r["lead_id"])


# ── bridge ──────────────────────────────────────────────────────────


def test_slug_is_douyin_video_comment() -> None:
    assert slug_for("video_comment", "douyin") == "douyin_video_comment"


def test_inputs_map_to_inputid_and_msg() -> None:
    inputs = _inputs_for(
        "video_comment",
        {"recipient": "dy_123", "customer_comment": "这个多少钱？", "lead_id": "l1"},
    )
    # D-b：不再下发 msg（正文由工作流执行期调 /inbound 取），改传客户那条评论
    assert inputs == {"inputid": "dy_123", "customer_comment": "这个多少钱？"}


def test_from_result_three_states() -> None:
    sent = from_result(
        "video_comment", {"sent_text": "讲得挺实用的"}, workflow_status="succeeded"
    )
    assert sent["comment_status"] == "sent"
    assert sent["sent_text"] == "讲得挺实用的"
    assert sent["no_video"] is False

    # 现网工作流出参常用 huifu_msg，与 sent_text 等价
    via_huifu = from_result(
        "video_comment",
        {"huifu_msg": "哈喽～刷到就是缘分"},
        workflow_status="succeeded",
    )
    assert via_huifu["comment_status"] == "sent"
    assert via_huifu["sent_text"] == "哈喽～刷到就是缘分"

    # 现网亦常把正文写在 posts[].text（output），无 sent_text/huifu_msg 时仍认成功
    via_posts = from_result(
        "video_comment",
        {"posts": [{"benchmark": "", "text": "讲得挺实用的～"}]},
        workflow_status="succeeded",
    )
    assert via_posts["comment_status"] == "sent"
    assert via_posts["sent_text"] == "讲得挺实用的～"

    no_video = from_result("video_comment", {"no_video": True}, workflow_status="succeeded")
    assert no_video["comment_status"] == "no_video"
    assert no_video["skip_reason"] == "无视频或私密账号"

    # 字符串 "true" 也认（automan 变量可能是文本）
    as_text = from_result("video_comment", {"no_video": "true"}, workflow_status="succeeded")
    assert as_text["comment_status"] == "no_video"

    # 兜底：工作流报成功但既无正文也无 no_video → 记跳过，不记查不出内容的成功
    blank = from_result("video_comment", {}, workflow_status="succeeded")
    assert blank["comment_status"] == "no_video"
    assert blank["skip_reason"] == "未取得评论内容"

    failed = from_result("video_comment", {"sent_text": "x"}, workflow_status="failed")
    assert failed["comment_status"] == "unknown"


# ── 终态回写 ────────────────────────────────────────────────────────


def test_success_marks_sent_without_touching_funnel(vc_env: Path) -> None:
    lead_id = _seed(vc_env, "dy_ok")
    before = get_lead(lead_id=lead_id, data_dir=vc_env)["funnel_stage"]
    apply_funnel_from_task(
        "douyin",
        "video_comment",
        {"recipient": "dy_ok", "customer_comment": "这个多少钱？", "lead_id": lead_id},
        from_result("video_comment", {"sent_text": "讲得挺实用的"}, workflow_status="succeeded"),
        data_dir=vc_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_SENT
    assert lead["funnel_stage"] == before  # 曝光类不推进漏斗


def test_no_video_marks_no_video(vc_env: Path) -> None:
    lead_id = _seed(vc_env, "dy_nv")
    apply_funnel_from_task(
        "douyin",
        "video_comment",
        {"recipient": "dy_nv", "customer_comment": "这个多少钱？", "lead_id": lead_id},
        from_result("video_comment", {"no_video": True}, workflow_status="succeeded"),
        data_dir=vc_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_NO_VIDEO
    assert lead["video_comment_checked_at"]
    assert list_lead_ids_pending_video_comment("douyin", data_dir=vc_env) == []


def test_failure_keeps_not_sent_and_retryable(vc_env: Path) -> None:
    lead_id = _seed(vc_env, "dy_fail")
    apply_funnel_from_task(
        "douyin",
        "video_comment",
        {"recipient": "dy_fail", "customer_comment": "这个多少钱？", "lead_id": lead_id},
        from_result("video_comment", {"sent_text": "x"}, workflow_status="failed"),
        data_dir=vc_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_NOT_SENT
    assert lead_id in list_lead_ids_pending_video_comment("douyin", data_dir=vc_env)


# ── WorkLog 字段 ────────────────────────────────────────────────────


def test_worklog_fields_are_script_and_contact(vc_env: Path) -> None:
    from plugins.mxai.orchestrator.models import Task
    from plugins.mxai.orchestrator.queue_manager import _video_comment_worklog_fields

    lead_id = _seed(vc_env, "dy_wl")
    task = Task(
        task_id="t1",
        profile_id="douyin",
        name="客户视频评论",
        task_type="video_comment",
        operator="test",
        payload={
            "recipient": "dy_wl",
            "customer_comment": "这个多少钱？",
            "lead_id": lead_id,
        },
    )
    task.payload["result"] = {"comment_status": "sent", "sent_text": "讲得挺实用的"}
    fields = _video_comment_worklog_fields(task)
    # 台账两列复用 CR-138 的「问:客户评论 · 答:我方评论」约定，前端已能解析
    assert fields["op_object"] == "客户 · 问:这个多少钱？ · 答:讲得挺实用的"
    assert fields["contact_id"] == "dy_wl"
    assert fields["display_name"] == "客户"

    # 跳过：答位写原因，客户评论仍在
    task.payload["result"] = {"comment_status": "no_video", "skip_reason": "无视频或私密账号"}
    assert (
        _video_comment_worklog_fields(task)["op_object"]
        == "客户 · 问:这个多少钱？ · 答:无视频或私密账号"
    )


def test_no_video_is_written_to_ledger_as_skipped() -> None:
    """CR-169 D-c：无作品/私密号**要写台账**（运营要看到结论），但状态记「跳过」。

    「跳过」既不计入成功数（_is_success 只认 成功/success），
    也不进失败率与风控告警（_FAIL_STATUSES / _ALERT_STATUSES 都不含它）。
    """
    import inspect

    from plugins.mxai.orchestrator import queue_manager
    from plugins.mxai.stats.service import _ALERT_STATUSES, _FAIL_STATUSES, _is_success

    src = inspect.getsource(queue_manager)
    assert 'wl_exec_status = "跳过"' in src, "no_video 应记「跳过」状态"
    assert "exec_status=wl_exec_status" in src, "append_worklog 须用动态状态而非写死成功"

    assert _is_success("跳过") is False
    assert "跳过" not in _FAIL_STATUSES
    assert "跳过" not in _ALERT_STATUSES


def test_touch_class_is_exposure() -> None:
    from plugins.mxai.worklog.touch_class import resolve_touch_class

    assert resolve_touch_class("video_comment") == "exposure"


# ── 会话隔离 / 台账互不污染（用户点名的两个坑）─────────────────────


def test_each_customer_gets_its_own_oneshot_session() -> None:
    """CR-146 one-shot：每个客户各自 ephemeral 会话，不复用同一个会话框。

    判定命中任一即可：feature=comment_reply，或绑定到评论智能体 profile。
    """
    from plugins.mxai.agents.session_ephemeral import (
        alloc_ephemeral_session,
        needs_oneshot_session,
    )

    assert needs_oneshot_session(binding_feature="comment_reply", hermes_profile="x") is True
    assert needs_oneshot_session(binding_feature=None, hermes_profile="douyin_comment") is True

    # 连续两次分配必须是不同会话（否则第二个客户会读到第一个的上下文）
    sid1, key1 = alloc_ephemeral_session("douyin_comment")
    sid2, key2 = alloc_ephemeral_session("douyin_comment")
    assert sid1 != sid2 and key1 != key2


def test_video_comment_does_not_pollute_ai_reply_ledger() -> None:
    """坑 A/B：/inbound 取文案不得把问答绑到视频评论任务，也不得产生 inbound_reply 日志。"""
    import inspect

    from plugins.mxai.api import agents as agents_api
    from plugins.mxai.orchestrator.queue_manager import QueueManager

    # 坑 A：绑定只认 inbound_reply 任务，video_comment 绑不上
    bind_src = inspect.getsource(QueueManager.bind_inbound_turn_to_listen_reply)
    assert 't.task_type == "inbound_reply"' in bind_src

    # 坑 B：/inbound 只返回文案，不写台账
    inbound_src = inspect.getsource(agents_api.inbound_message)
    assert "append_worklog" not in inbound_src
