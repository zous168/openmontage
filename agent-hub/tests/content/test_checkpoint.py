"""Checkpoint head upsert · 单轨（step_raw 产物 dict + stage_status 全量显式，LT-055 P2）。

初版无存量数据：不再有 stage / legacy_stage / legacy_step_raw 与旧数据推断。
"""

from __future__ import annotations

from plugins.mxai.content.checkpoint import is_stage_id
from plugins.mxai.content.create_history import (
    KIND_VIRAL_CLONE,
    get_history,
    list_history,
    save_history,
)


def test_save_params_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/new.mp4",
        shots=[],
        stage_status={"params": "done", "reverse": "pending"},
        params={"aspect": "9:16", "max_shots": 4},
        copy_confirmed=False,
    )
    assert saved["session_id"] == saved["id"]
    assert saved["step_raw"] == {}
    assert saved["stage_status"]["params"] == "done"
    assert saved["params"]["aspect"] == "9:16"
    assert saved["shot_count"] == 0


def test_save_step_raw_dict_single_track(tmp_path, monkeypatch) -> None:
    """步骤产物 dict 直存 step_raw（单轨，无 legacy_step_raw）。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/a.mp4",
        model="qwen-vl-max",
        shots=[{"title": "开场", "duration_sec": 3, "prompt": "产品特写痛点字幕足够长"}],
        step_raw={"reverse": {"raw": "model-original", "mock": True}},
        stage_status={"params": "done", "reverse": "done", "copy_rewrite": "pending"},
    )
    assert saved["step_raw"]["reverse"]["raw"] == "model-original"
    assert "reverse" in saved["step_raw_keys"]
    assert "legacy_step_raw" not in saved
    assert "stage" not in saved
    assert "legacy_stage" not in saved


def test_params_then_reverse_advances_checkpoint(tmp_path, monkeypatch) -> None:
    """入队先落 params 后写入 reverse 产物：stage_status 显式推进，勿锁在 params。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    first = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/queue.mp4",
        shots=[],
        stage_status={"params": "done", "reverse": "pending"},
        params={"aspect": "9:16"},
    )
    sid = first["id"]
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/queue.mp4",
        model="MiniMax-M2.7",
        shots=[{"title": "开场", "duration_sec": 10, "prompt": "工厂口播走播提示词足够长用于测试"}],
        step_raw={"reverse": {"raw": "llm-json", "request": {"model": "MiniMax-M2.7", "user": "brief"}}},
        stage_status={"params": "done", "reverse": "done", "copy_rewrite": "pending"},
    )
    assert saved["id"] == sid
    assert saved["step_raw"]["reverse"]["request"]["model"] == "MiniMax-M2.7"
    assert saved["stage_status"]["params"] == "done"
    assert saved["stage_status"]["reverse"] == "done"


def test_list_includes_session_id_and_stage_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/b.mp4",
        shots=[{"title": "镜1", "duration_sec": 5, "prompt": "改写后的提示词足够长用于测试"}],
        step_raw={"reverse": {"ok": True}},
        stage_status={"reverse": "done", "shot_edit": "running"},
    )
    listed = list_history(KIND_VIRAL_CLONE)
    row = listed["items"][0]
    assert row["session_id"] == saved["id"]
    assert row["step_raw"]["reverse"]["ok"] is True
    assert "reverse:done" in row["stage_status_summary"]


def test_single_track_roundtrip(tmp_path, monkeypatch) -> None:
    """单轨直存：产物 + 状态显式保存后可完整读回（无推断）。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/old.mp4",
        model="wan2.6-t2v",
        shots=[
            {
                "title": "镜1",
                "duration_sec": 5,
                "prompt": "旧历史分镜提示词足够长",
                "preview_url": "https://cdn.example.com/out.mp4",
            },
        ],
        step_raw={"reverse": {"ok": True}, "generate": {"clips": [{"id": 1}]}},
        stage_status={
            "params": "done", "reverse": "done", "copy_rewrite": "done",
            "shot_edit": "done", "generate": "done", "voice": "skipped", "compose": "pending",
        },
    )
    detail = get_history(KIND_VIRAL_CLONE, saved["id"])
    assert detail["step_raw"]["generate"]["clips"][0]["id"] == 1
    assert detail["stage_status"]["generate"] == "done"
    assert detail["stage_status"]["voice"] == "skipped"
    assert detail["stage_status"]["compose"] == "pending"


def test_checkpoint_route_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    created = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/c.mp4",
        shots=[{"title": "t", "duration_sec": 3, "prompt": "足够长的分镜提示词内容"}],
        stage_status={"params": "done", "reverse": "done"},
    )
    updated = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=created["id"],
        source_url="https://cdn.example.com/c.mp4",
        shots=[{"title": "t", "duration_sec": 3, "prompt": "足够长的分镜提示词内容"}],
        step_raw={"copy_rewrite": {"applied": True}},
        stage_status={"params": "done", "reverse": "done", "copy_rewrite": "done"},
        copy_confirmed=False,
    )
    assert updated["step_raw"]["copy_rewrite"]["applied"] is True


def test_rerun_reverse_invalidates_downstream(tmp_path, monkeypatch) -> None:
    """第一步重新生成：裁掉下游 step_raw 产物，stage_status 回 pending，分镜清空。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    first = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/rerun.mp4",
        shots=[{"title": "旧镜", "duration_sec": 5, "prompt": "旧提示词足够长用于测试", "preview_url": "https://cdn.example.com/old.mp4"}],
        step_raw={
            "reverse": {"ok": True},
            "copy_rewrite": {"applied": True},
            "generate": {"clips": [{"id": "s1"}]},
            "compose": {"draft_name": "x.draft"},
        },
        stage_status={
            "params": "done",
            "reverse": "done",
            "copy_rewrite": "done",
            "shot_edit": "done",
            "generate": "done",
            "voice": "skipped",
            "compose": "done",
        },
        copy_confirmed=True,
    )
    sid = first["id"]

    invalidated = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/rerun.mp4",
        shots=[],
        invalidate_from="reverse",
        copy_confirmed=False,
    )
    assert invalidated["shots"] == []
    assert invalidated["copy_confirmed"] is False
    assert "copy_rewrite" not in (invalidated.get("step_raw") or {})
    assert "generate" not in (invalidated.get("step_raw") or {})
    assert invalidated["stage_status"]["params"] == "done"
    assert invalidated["stage_status"]["reverse"] == "pending"
    assert invalidated["stage_status"]["copy_rewrite"] == "pending"
    assert invalidated["stage_status"]["shot_edit"] == "pending"
    assert invalidated["stage_status"]["generate"] == "pending"
    assert invalidated["stage_status"]["compose"] == "pending"

    rerun = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/rerun.mp4",
        shots=[{"title": "新镜", "duration_sec": 10, "prompt": "新提示词足够长用于测试重跑失效"}],
        step_raw={"reverse": {"ok": True, "raw": "new"}},
        stage_status={"params": "done", "reverse": "done"},
        copy_confirmed=False,
    )
    assert len(rerun["shots"]) == 1
    assert rerun["shots"][0]["title"] == "新镜"
    assert rerun["step_raw"].get("reverse", {}).get("raw") == "new"
    assert "generate" not in (rerun.get("step_raw") or {})
    assert "compose" not in (rerun.get("step_raw") or {})
    assert rerun["stage_status"]["reverse"] == "done"
    assert rerun["stage_status"]["copy_rewrite"] == "pending"
    assert rerun["stage_status"]["generate"] == "pending"
    assert rerun["stage_status"]["compose"] == "pending"
    assert rerun["copy_confirmed"] is False
