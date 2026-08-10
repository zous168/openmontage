"""Clearer tool lines in runs/*.log — not a new audit surface."""

from __future__ import annotations

import json

from plugins.openmontage.backlot.stage_runner import render_run_log
from plugins.openmontage.lib.tool_log import summarize_tool_call


def test_summarize_registry_and_checkpoint():
    fail = summarize_tool_call(
        "om_registry",
        {
            "action": "execute",
            "tool": "export_bundle",
            "label": "打包",
            "params": {"video_path": "projects/demo/renders/final.mp4", "title": "T"},
        },
        {"ok": False, "result": {"success": False, "error": "video_path not found"}},
    )
    assert fail["ok"] is False
    assert "export_bundle" in fail["summary"]
    assert "FAIL" in fail["summary"]

    ckpt = summarize_tool_call(
        "om_checkpoint",
        {"status": "awaiting_human", "artifacts": {"script": {}}},
        {"ok": True},
    )
    assert ckpt["ok"] is True
    assert "awaiting_human" in ckpt["summary"]
    assert "script" in ckpt["summary"]


def test_render_tool_action_line():
    raw = json.dumps({
        "type": "system",
        "subtype": "tool_action",
        "ok": True,
        "summary": "om_artifact_write artifacts/script.json (120 B)",
        "label": "写脚本",
    }, ensure_ascii=False)
    lines = render_run_log(raw)
    assert any("✓ om_artifact_write" in line and "写脚本" in line for line in lines)
