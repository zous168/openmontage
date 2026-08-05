"""CR-132 · pending-add-contacts 兼容路由 + 结构化导入（数据落 add_records）."""

from __future__ import annotations

import io

from plugins.mxai.api.deps import get_queue


def test_pending_import_enqueue_flow(mxai_client, mxai_env) -> None:
    q = get_queue()
    q.set_agent_enabled("wechat", True)

    r1 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/import",
        json={"text": "user_a\nuser_b\n"},
    )
    assert r1.status_code == 200
    assert r1.json()["added"] == 2

    lst = mxai_client.get("/api/plugins/mxai/agents/wechat/pending-add-contacts")
    assert lst.status_code == 200
    assert lst.json()["total"] == 2

    r2 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/import",
        json={"text": "user_a"},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "duplicates"

    enq = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/enqueue",
        json={"all_pending": True},
    )
    assert enq.status_code == 200
    body = enq.json()
    assert body["queued"] == 2
    assert len(body["task_ids"]) == 2


def test_pending_delete_row(mxai_client) -> None:
    # CR-132：pending-add-contacts 兼容路由返回 add_records 记录（主键 record_id）
    mxai_client.post(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/import",
        json={"text": "del_me"},
    )
    row = mxai_client.get("/api/plugins/mxai/agents/wechat/pending-add-contacts").json()["items"][0]
    del_r = mxai_client.delete(
        f"/api/plugins/mxai/agents/wechat/pending-add-contacts/{row['record_id']}"
    )
    assert del_r.status_code == 200
    assert mxai_client.get("/api/plugins/mxai/agents/wechat/pending-add-contacts").json()["total"] == 0


def test_structured_csv_import(mxai_client) -> None:
    csv_bytes = "客户名,微信号\n张三,wx_zhang\n,wx_no_name\n".encode("utf-8")
    files = {"file": ("contacts.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/import",
        files=files,
    )
    assert r.status_code == 200
    assert r.json()["added"] == 2


def test_download_pending_add_template(mxai_client, tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from plugins.mxai.contacts.pending_add_local_exports import list_templates, template_filename
    from plugins.mxai.contacts.structured_parser import parse_structured_file

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    wx = mxai_client.get("/api/plugins/mxai/agents/wechat/pending-add-contacts/template")
    assert wx.status_code == 200
    assert "spreadsheetml" in (wx.headers.get("content-type") or "")
    parsed = parse_structured_file(wx.content, "批量添加好友模板.xlsx")
    assert parsed.rows[0].contact_id == "wxid_example"

    listed_wx = list_templates("wechat")
    assert listed_wx["profile_id"] == "wechat"
    assert any(i["name"] == template_filename("wechat") for i in listed_wx["items"])
    api_list = mxai_client.get(
        "/api/plugins/mxai/agents/wechat/pending-add-contacts/local-templates"
    )
    assert api_list.status_code == 200
    assert api_list.json()["profile_id"] == "wechat"
    assert api_list.json()["items"]

    ww = mxai_client.get("/api/plugins/mxai/agents/qiyeweixin/add-records/template")
    assert ww.status_code == 200
    assert ww.content[:2] == b"PK"
    listed_qw = mxai_client.get(
        "/api/plugins/mxai/agents/qiyeweixin/add-records/local-templates"
    ).json()
    assert listed_qw["profile_id"] == "qiyeweixin"
    assert any(i["name"] == template_filename("qiyeweixin") for i in listed_qw["items"])
    # 渠道隔离：个微列表不含企微文件名
    assert all(i["name"] != template_filename("qiyeweixin") for i in api_list.json()["items"])


def test_worklogs_op_type_filter(mxai_client, mxai_env) -> None:
    from plugins.mxai.worklog.service import append_worklog

    append_worklog(
        profile_id="wechat",
        op_type="add_friends",
        exec_status="成功",
        contact_id="c1",
        data_dir=mxai_env,
    )
    append_worklog(
        profile_id="wechat",
        op_type="scheduled_msg",
        exec_status="成功",
        data_dir=mxai_env,
    )
    all_logs = mxai_client.get("/api/plugins/mxai/agents/wechat/worklogs?limit=20").json()
    add_only = mxai_client.get(
        "/api/plugins/mxai/agents/wechat/worklogs?limit=20&op_type=add_friends"
    ).json()
    assert add_only["total"] >= 1
    assert all(i["op_type"] == "add_friends" for i in add_only["items"])
    assert add_only["total"] <= all_logs["total"]
