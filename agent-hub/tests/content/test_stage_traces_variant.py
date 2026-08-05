"""StageTrace variant：分镜 AI / 片段生成按镜保留。"""

from __future__ import annotations

from plugins.mxai.content.assist import complete_content_assist
from plugins.mxai.content.stage_traces import list_traces, resolve_trace_title, write_trace


def test_write_trace_keeps_latest_per_variant(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    sid = "sess-variant-1"
    write_trace(sid, stage="generate", assembled="a1", variant="shot-a", structured={"n": 1})
    write_trace(sid, stage="generate", assembled="a2", variant="shot-a", structured={"n": 2})
    write_trace(sid, stage="generate", assembled="b1", variant="shot-b", structured={"n": 3})

    listed = list_traces(sid, limit=20, latest_only=True)
    items = listed["items"]
    generate_items = [x for x in items if x.get("stage") == "generate"]
    assert len(generate_items) == 2
    by_var = {x.get("variant"): x for x in generate_items}
    assert "shot-a" in by_var and "shot-b" in by_var
    from plugins.mxai.content.stage_traces import get_latest_trace, get_trace

    # shot-a 只留最新 a2
    detail_a = get_trace(sid, by_var["shot-a"]["run_id"])
    assert detail_a.get("assembled") == "a2"
    latest = get_latest_trace(sid, "generate")
    assert latest is not None
    assert latest.get("assembled") in ("a2", "b1")


def test_resolve_trace_title_by_scene() -> None:
    assert resolve_trace_title("reverse") == "反推镜头提示词"
    assert resolve_trace_title("copy_rewrite", structured={"shot_count": 3}) == "文案改写 · 3 镜"
    assert resolve_trace_title("generate", title="镜头 2") == "镜头 2"
    assert resolve_trace_title("generate", variant="2") == "片段生成 · 2"
    assert resolve_trace_title("shot_edit", structured={"shot_title": "开场钩子"}) == "开场钩子"


def test_write_trace_persists_scene_title(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    sid = "sess-title-1"
    write_trace(
        sid,
        stage="generate",
        assembled="### USER\np",
        raw_output={"ok": 1},
        variant="1",
        title="镜头 1",
    )
    listed = list_traces(sid, stage="generate", latest_only=True)
    assert listed["items"][0]["title"] == "镜头 1"
    from plugins.mxai.content.stage_traces import get_trace

    detail = get_trace(sid, listed["items"][0]["run_id"])
    assert detail.get("title") == "镜头 1"


def test_write_with_variant_purges_orphan_no_variant(tmp_path, monkeypatch) -> None:
    """升级前 job 收尾会写无 variant 空壳；正式按镜写入后应清掉。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    sid = "sess-orphan-1"
    write_trace(sid, stage="generate", structured={"status": "completed", "shot_id": "3"})
    write_trace(
        sid,
        stage="generate",
        assembled="### USER\nprompt-1",
        raw_output={"ok": True},
        variant="1",
        structured={"shot_title": "镜1"},
    )
    listed = list_traces(sid, stage="generate", latest_only=True)
    items = listed["items"]
    assert len(items) == 1
    assert items[0].get("variant") == "1"
    assert items[0].get("has_assembled") is True


def test_assist_writes_shot_edit_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    sid = "sess-assist-1"
    res = complete_content_assist(
        scene="video_shot_prompt",
        fmt="plain",
        content="工厂口播走播，手持轻微颠簸",
        mode="optimize",
        context={"shot_id": "s1", "label": "第1镜"},
        session_id=sid,
    )
    assert res.get("content")
    listed = list_traces(sid, stage="shot_edit", latest_only=True)
    assert listed["total"] >= 1
    row = listed["items"][0]
    assert row["stage"] == "shot_edit"
    assert row.get("variant") == "s1"
    assert row.get("has_assembled") is True
    assert row.get("has_raw_output") is True
