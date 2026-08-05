"""CR-132 · add-records API + 运行时段 + 队列回写 集成单测."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import core.timeutil as tu
from plugins.mxai.contacts.structured_parser import ContactRow

_BASE = "/api/plugins/mxai/agents/wechat"
_BJ = timezone(timedelta(hours=8))


def test_import_and_dual_filter(mxai_client) -> None:
    r = mxai_client.post(f"{_BASE}/add-records/import", json={"contacts": ["wxid_a", "wxid_b"]})
    assert r.status_code == 200 and r.json()["added"] == 2

    allrec = mxai_client.get(f"{_BASE}/add-records").json()
    assert allrec["total"] == 2
    assert {rec["import_source"] for rec in allrec["records"]} == {"manual"}
    assert {rec["import_source_label"] for rec in allrec["records"]} == {"手工导入"}

    # 状态×来源双重筛选 AND
    hit = mxai_client.get(f"{_BASE}/add-records", params={"status": "pending", "source": "manual"})
    assert hit.json()["total"] == 2
    miss = mxai_client.get(f"{_BASE}/add-records", params={"status": "success"})
    assert miss.json()["total"] == 0
    # 来源不匹配 → 空（AND）
    none = mxai_client.get(f"{_BASE}/add-records", params={"status": "pending", "source": "douyin"})
    assert none.json()["total"] == 0


def test_import_source_boss_and_default_manual(mxai_client) -> None:
    """缺省/显式 manual → 手工导入；显式 boss → BOSS；互不影响。"""
    r_manual = mxai_client.post(
        f"{_BASE}/add-records/import", json={"contacts": ["wxid_manual_only"]}
    )
    assert r_manual.status_code == 200
    r_boss = mxai_client.post(
        f"{_BASE}/add-records/import",
        json={"contacts": ["wxid_from_boss"], "import_source": "boss"},
    )
    assert r_boss.status_code == 200

    by_id = {
        rec["contact_id"]: rec
        for rec in mxai_client.get(f"{_BASE}/add-records").json()["records"]
    }
    assert by_id["wxid_manual_only"]["import_source"] == "manual"
    assert by_id["wxid_manual_only"]["import_source_label"] == "手工导入"
    assert by_id["wxid_from_boss"]["import_source"] == "boss"
    assert by_id["wxid_from_boss"]["import_source_label"] == "BOSS"

    assert mxai_client.get(
        f"{_BASE}/add-records", params={"source": "boss"}
    ).json()["total"] == 1
    assert mxai_client.get(
        f"{_BASE}/add-records", params={"source": "manual"}
    ).json()["total"] == 1

    bad = mxai_client.post(
        f"{_BASE}/add-records/import",
        json={"contacts": ["wxid_bad"], "import_source": "not_a_source"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "invalid_import_source"


def test_import_rows_with_display_name(mxai_client) -> None:
    """结构化 rows 可带客户名；旧 contacts 仍无客户名。"""
    r = mxai_client.post(
        f"{_BASE}/add-records/import",
        json={
            "rows": [
                {"display_name": "宋学成", "contact_id": "wxid_song"},
                {"display_name": "", "contact_id": "wxid_anon"},
            ],
            "import_source": "boss",
        },
    )
    assert r.status_code == 200 and r.json()["added"] == 2
    by_id = {
        rec["contact_id"]: rec
        for rec in mxai_client.get(f"{_BASE}/add-records").json()["records"]
    }
    assert by_id["wxid_song"]["display_name"] == "宋学成"
    assert by_id["wxid_song"]["import_source"] == "boss"
    assert by_id["wxid_anon"]["display_name"] in (None, "", "—") or not by_id[
        "wxid_anon"
    ].get("display_name")

    legacy = mxai_client.post(
        f"{_BASE}/add-records/import", json={"contacts": ["wxid_legacy_name"]}
    )
    assert legacy.status_code == 200
    leg = next(
        rec
        for rec in mxai_client.get(f"{_BASE}/add-records").json()["records"]
        if rec["contact_id"] == "wxid_legacy_name"
    )
    assert not (leg.get("display_name") or "").strip()
    assert leg["import_source"] == "manual"


def test_retry_only_failed_and_delete(mxai_client) -> None:
    mxai_client.post(f"{_BASE}/add-records/import", json={"contacts": ["wxid_x"]})
    rid = mxai_client.get(f"{_BASE}/add-records").json()["records"][0]["record_id"]
    # pending 记录 retry → 404（仅 failed 可重新添加）
    assert mxai_client.post(f"{_BASE}/add-records/{rid}/retry").status_code == 404
    # 删除
    assert mxai_client.delete(f"{_BASE}/add-records/{rid}").status_code == 200
    assert mxai_client.get(f"{_BASE}/add-records").json()["total"] == 0


def test_retry_failed_becomes_pending(mxai_client) -> None:
    """失败点「重新添加」须回到 pending，并出现在待添加列表。"""
    from plugins.mxai.crm.add_records import service as svc

    mxai_client.post(f"{_BASE}/add-records/import", json={"contacts": ["wxid_retry"]})
    rid = mxai_client.get(f"{_BASE}/add-records").json()["records"][0]["record_id"]
    svc.mark_failed("wechat", "wxid_retry", reason="超时")
    assert mxai_client.get(f"{_BASE}/add-records", params={"status": "failed"}).json()["total"] == 1

    r = mxai_client.post(f"{_BASE}/add-records/{rid}/retry")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    pending = mxai_client.get(f"{_BASE}/pending-add-contacts").json()
    assert pending["total"] == 1
    assert pending["items"][0]["record_id"] == rid
    assert pending["items"][0]["status"] == "pending"
    assert mxai_client.get(f"{_BASE}/add-records", params={"status": "failed"}).json()["total"] == 0
    assert mxai_client.get(f"{_BASE}/add-records", params={"status": "pending"}).json()["total"] == 1


def test_api_channel_isolation(mxai_client) -> None:
    mxai_client.post(f"{_BASE}/add-records/import", json={"contacts": ["shared"]})
    mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/add-records/import", json={"contacts": ["shared"]}
    )
    assert mxai_client.get(f"{_BASE}/add-records").json()["total"] == 1
    ww = mxai_client.get("/api/plugins/mxai/agents/qiyeweixin/add-records").json()
    assert ww["total"] == 1
    # op_type 随渠道
    assert mxai_client.get(f"{_BASE}/add-records").json()["records"][0]["op_type"] == "add_friends"
    assert ww["records"][0]["op_type"] == "add_contacts"


def test_within_run_window_logic(monkeypatch) -> None:
    from plugins.mxai.api import agents

    monkeypatch.setattr(
        agents, "_read_workbench", lambda a: {"add_friends": {"run_window": {"start": "08:00", "end": "09:00"}}}
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 3, 12, 0, tzinfo=_BJ))
    assert agents._within_run_window("wechat")[0] is False  # 窗口外
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 3, 8, 30, tzinfo=_BJ))
    assert agents._within_run_window("wechat")[0] is True  # 窗口内
    # 跨零点窗口 22:00–06:00
    monkeypatch.setattr(
        agents, "_read_workbench", lambda a: {"add_friends": {"run_window": {"start": "22:00", "end": "06:00"}}}
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 3, 23, 30, tzinfo=_BJ))
    assert agents._within_run_window("wechat")[0] is True
    # 未配置 = 不限制
    monkeypatch.setattr(agents, "_read_workbench", lambda a: {"add_friends": {}})
    assert agents._within_run_window("wechat")[0] is True
    # 企微读 batch_add 时段
    monkeypatch.setattr(
        agents,
        "_read_workbench",
        lambda a: {"batch_add": {"run_window": {"start": "08:00", "end": "09:00"}}},
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 3, 12, 0, tzinfo=_BJ))
    assert agents._within_run_window("qiyeweixin")[0] is False
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 3, 8, 30, tzinfo=_BJ))
    assert agents._within_run_window("qiyeweixin")[0] is True


def test_manual_enqueue_bypasses_run_window(mxai_client, monkeypatch) -> None:
    """CR-151：用户点击「开始添加」不受 run_window 限制."""
    mxai_client.post(f"{_BASE}/add-records/import", json={"contacts": ["wxid_r"]})
    from plugins.mxai.api import agents

    monkeypatch.setattr(agents, "_within_run_window", lambda a: (False, "08:00", "09:00"))
    r = mxai_client.post(f"{_BASE}/add-records/enqueue", json={"all_pending": True})
    assert r.status_code == 200
    assert r.json().get("queued", 0) >= 1


def test_queue_outcome_writes_status(mxai_env) -> None:
    """CR-132 关键语义：成功→保留 success 态（不删）；失败→failed 态."""
    from plugins.mxai.crm.add_records import service as svc
    from plugins.mxai.orchestrator.queue_manager import _pending_add_outcome

    svc.import_rows("wechat", [ContactRow(display_name="A", contact_id="c_ok", row_num=1)])
    svc.import_rows("wechat", [ContactRow(display_name="B", contact_id="c_bad", row_num=1)])

    _pending_add_outcome(
        SimpleNamespace(task_type="add_friends", payload={"contact_id": "c_ok"}, profile_id="wechat"),
        success=True,
    )
    _pending_add_outcome(
        SimpleNamespace(
            task_type="add_friends",
            payload={"contact_id": "c_bad", "fail_reason": "风控拦截"},
            profile_id="wechat",
            fail_reason="",
        ),
        success=False,
    )

    ok = svc.find_by_contact("wechat", "c_ok")
    bad = svc.find_by_contact("wechat", "c_bad")
    assert ok["status"] == "success"  # 保留，未删除
    assert bad["status"] == "failed" and bad["failed_reason"] == "风控拦截"

    # 任务终态 fail_reason 优先于空 payload
    svc.import_rows("wechat", [ContactRow(display_name="C", contact_id="c_exc", row_num=1)])
    _pending_add_outcome(
        SimpleNamespace(
            task_type="add_friends",
            payload={"contact_id": "c_exc"},
            profile_id="wechat",
            fail_reason="RPA 超时",
        ),
        success=False,
    )
    exc_row = svc.find_by_contact("wechat", "c_exc")
    assert exc_row["status"] == "failed" and exc_row["failed_reason"] == "RPA 超时"
