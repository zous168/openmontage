"""本机周报导出目录落盘与列表."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.reports import local_exports as le


def test_save_list_export_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(le, "weekly_report_dir", lambda: tmp_path / "MxAI" / "周报")
    saved = le.save_export_bytes("MxAI-周报-2026-07-23.xlsx", b"PK\x03\x04fake")
    assert Path(saved["path"]).is_file()
    listed = le.list_exports()
    assert listed["dir"] == str((tmp_path / "MxAI" / "周报").resolve())
    assert len(listed["items"]) == 1
    assert listed["items"][0]["name"] == "MxAI-周报-2026-07-23.xlsx"
    resolved = le.resolve_export_file("MxAI-周报-2026-07-23.xlsx")
    assert resolved.name == "MxAI-周报-2026-07-23.xlsx"


def test_sanitize_rejects_traversal() -> None:
    try:
        le.sanitize_filename("../evil.xlsx")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_export_filename_weekly() -> None:
    name = le.export_filename("weekly")
    assert name.startswith("MxAI-周报-")
    assert name.endswith(".xlsx")


def test_reports_export_persists_and_lists(mxai_client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(le, "weekly_report_dir", lambda: tmp_path / "MxAI" / "周报")
    gen = mxai_client.post(
        "/api/plugins/mxai/reports/generate",
        json={"report_type": "weekly"},
    )
    assert gen.status_code == 200
    report_id = gen.json()["report_id"]
    export = mxai_client.post(f"/api/plugins/mxai/reports/{report_id}/export")
    assert export.status_code == 200
    listed = mxai_client.get("/api/plugins/mxai/reports/local-exports")
    assert listed.status_code == 200
    body = listed.json()
    assert body["items"], "export should write at least one xlsx"
    assert any(i["name"].startswith("MxAI-周报-") for i in body["items"])
    name = body["items"][0]["name"]
    file_res = mxai_client.get(f"/api/plugins/mxai/reports/local-exports/{name}")
    assert file_res.status_code == 200
    assert file_res.content[:2] == b"PK"
