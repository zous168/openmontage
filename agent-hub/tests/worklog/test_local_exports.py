"""本机工作明细导出目录落盘与列表（按渠道隔离）."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.worklog import local_exports as le


def test_save_list_isolated_by_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(le, "_docs_root", lambda: tmp_path / "MxAI" / "工作明细")
    le.save_export_bytes(
        "MxAI-工作明细-qiyeweixin-2026-07-24-120000.csv",
        b"\ufeffqw\n",
        profile_id="qiyeweixin",
    )
    le.save_export_bytes(
        "MxAI-工作明细-wechat-2026-07-24-120001.csv",
        b"\ufeffwx\n",
        profile_id="wechat",
    )
    qw = le.list_exports(profile_id="qiyeweixin")
    wx = le.list_exports(profile_id="wechat")
    assert len(qw["items"]) == 1
    assert "qiyeweixin" in qw["items"][0]["name"]
    assert qw["dir"].endswith(str(Path("qiyeweixin")))
    assert len(wx["items"]) == 1
    assert "wechat" in wx["items"][0]["name"]
    assert all("wechat" in i["name"] for i in wx["items"])
    assert all("qiyeweixin" not in i["name"] for i in wx["items"])


def test_sanitize_rejects_traversal() -> None:
    try:
        le.sanitize_filename("../evil.csv")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_export_filename_profile() -> None:
    name = le.export_filename(profile_id="wechat")
    assert name.startswith("MxAI-工作明细-wechat-")
    assert name.endswith(".csv")


def test_worklogs_export_persists_and_lists(mxai_client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(le, "_docs_root", lambda: tmp_path / "MxAI" / "工作明细")
    res = mxai_client.post(
        "/api/plugins/mxai/worklogs/export",
        json={"profile_id": "wechat", "limit": 10},
    )
    assert res.status_code == 200
    listed = mxai_client.get(
        "/api/plugins/mxai/worklogs/local-exports",
        params={"profile_id": "wechat"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body.get("profile_id") == "wechat"
    assert "wechat" in str(body.get("dir") or "")
    assert any(str(i.get("name") or "").endswith(".csv") for i in body.get("items") or [])
    other = mxai_client.get(
        "/api/plugins/mxai/worklogs/local-exports",
        params={"profile_id": "qiyeweixin"},
    )
    assert other.status_code == 200
    assert other.json().get("items") == []
