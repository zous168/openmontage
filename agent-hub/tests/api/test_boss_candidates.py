"""Boss GET /candidates：主源为 boss_greet_leads."""

from plugins.mxai.crm.boss_candidates import (
    boss_display_name,
    boss_position_from_greet_op,
    candidate_from_worklog,
    list_boss_candidates,
)
from plugins.mxai.crm.boss_greet_leads import register_greet_lead
from plugins.mxai.worklog.service import append_worklog


def test_candidate_from_recruit_worklog() -> None:
    row = {
        "op_type": "招聘沟通",
        "op_object": "候选人#前端-李工 · 问:方便聊聊薪资吗 · 答:15-25K",
        "exec_status": "成功",
    }
    item = candidate_from_worklog(row)
    assert item is not None
    assert item["id"] == "候选人#前端-李工"
    assert item["name"] == "前端-李工"
    # 岗位仅来自打招呼登记 / greet WorkLog，招聘沟通摘要不含职位
    assert item["job"] == "—"
    assert item["stage"] == "沟通中"
    assert "city" not in item


def test_candidate_from_greet_worklog_keeps_position() -> None:
    row = {
        "op_type": "greet",
        "op_object": "李先生 · 私域合伙人(纯合伙制操盘岗位) · 岗位职能匹配，经验充足",
        "exec_status": "成功",
    }
    item = candidate_from_worklog(row)
    assert item is not None
    assert item["name"] == "李先生"
    assert item["job"] == "私域合伙人(纯合伙制操盘岗位)"
    assert item["stage"] == "已打招呼"
    assert boss_position_from_greet_op("打招呼", row["op_object"]) == item["job"]


def test_candidate_job_from_greet_lead() -> None:
    row = {
        "op_type": "招聘沟通",
        "op_object": "候选人#李先生 · 问:还招人吗 · 答:在招",
        "exec_status": "成功",
    }
    item = candidate_from_worklog(
        row,
        lead_positions={"李先生": "私域合伙人(纯合伙制操盘岗位)"},
    )
    assert item is not None
    assert item["job"] == "私域合伙人(纯合伙制操盘岗位)"


def test_inbound_reply_excluded() -> None:
    row = {
        "op_type": "inbound_reply",
        "op_object": "mock_boss_nea6 · 问:您好 · 答:Bot",
        "exec_status": "成功",
    }
    assert candidate_from_worklog(row) is None


def test_greet_position_only_worklog_not_candidate() -> None:
    """任务完成伪台账：op_object 仅职位 → 不得进候选人."""
    assert (
        candidate_from_worklog(
            {
                "op_type": "greet",
                "op_object": "新媒体销售专员",
                "exec_status": "成功",
            }
        )
        is None
    )
    assert (
        candidate_from_worklog(
            {
                "op_type": "打招呼",
                "op_object": "新媒体销售专员 · 新媒体销售专员 · 误登记",
                "exec_status": "成功",
            }
        )
        is None
    )


def test_list_dedupes_by_peer(mxai_env) -> None:
    del mxai_env
    append_worklog(
        profile_id="boss",
        op_type="招聘沟通",
        exec_status="成功",
        op_object="候选人#王女士 · 问:还招人吗 · 答:在招",
    )
    append_worklog(
        profile_id="boss",
        op_type="招聘沟通",
        exec_status="成功",
        op_object="候选人#王女士 · 问:二面时间 · 答:下周",
    )
    from plugins.mxai.worklog.service import list_worklogs

    rows = list_worklogs(profile_id="boss", limit=20)
    items = list_boss_candidates(rows, limit=10)
    wang = [c for c in items if c["name"] == "王女士"]
    assert len(wang) == 1


def test_boss_candidates_api_from_greet_leads(mxai_client, mxai_env) -> None:
    """候选人 API 以 greet 登记为主源，不再吃 worklog 职位伪行."""
    del mxai_env
    append_worklog(
        profile_id="boss",
        op_type="greet",
        exec_status="成功",
        op_object="新媒体销售专员 · 新媒体销售专员 · 批量打招呼",
    )
    register_greet_lead(
        "boss",
        name="张媛媛",
        reason="简历匹配",
        position="新媒体销售专员",
    )
    res = mxai_client.get("/api/plugins/mxai/agents/boss/candidates").json()
    names = [c["name"] for c in res["items"]]
    assert "张媛媛" in names
    assert "新媒体销售专员" not in names
    item = next(c for c in res["items"] if c["name"] == "张媛媛")
    assert item["job"] == "新媒体销售专员"
    assert "city" not in item


def test_boss_display_name_strips_prefix() -> None:
    assert boss_display_name("候选人#李工") == "李工"
