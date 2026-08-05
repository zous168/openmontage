"""仿爆款剪辑方案 + 剪映草稿目录导出。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from plugins.mxai.content.capcut_draft import (
    build_draft_content,
    export_compose_draft,
    resolve_jianying_drafts_dir,
)
from plugins.mxai.content.compose_plan import (
    build_heuristic_plan,
    generate_compose_plan,
    parse_compose_plan,
)


def _sample_shots() -> list[dict]:
    return [
        {
            "id": 1,
            "title": "开场",
            "duration_sec": 13,
            "copy": "你是不是也试过十几种方法？",
            "visual_timeline": [
                {
                    "t_start": "00:00",
                    "t_end": "00:04",
                    "camera": "中景",
                    "action": "口播",
                    "fx": None,
                    "cut": None,
                },
                {
                    "t_start": "00:04",
                    "t_end": "00:09",
                    "camera": "近景",
                    "action": "展示产品",
                    "fx": "右下角 PiP [75%,70%,20%,25%]，圆角+2px白边",
                    "cut": "Cut 硬切 @ 段内+4s",
                },
            ],
            "preview_url": "",
        },
        {
            "id": 2,
            "title": "收束",
            "duration_sec": 13,
            "copy": "评论区扣1发清单",
            "visual_timeline": [],
            "preview_url": "",
        },
    ]


def test_heuristic_plan_has_main_and_pip() -> None:
    plan = build_heuristic_plan(_sample_shots(), source_copy={"hook": "钩子"})
    assert plan["canvas"]["ratio"] == "9:16"
    assert len(plan["tracks"]["main_video"]) == 2
    assert plan["total_duration_sec"] == 26
    assert len(plan["tracks"]["pip_video"]) >= 1
    rect = plan["tracks"]["pip_video"][0]["rect_norm"]
    assert abs(rect[0] - 0.75) < 0.02
    assert plan["tracks"]["subtitle"]


def test_parse_compose_plan() -> None:
    raw = """
{
  "canvas": {"width": 1080, "height": 1920, "fps": 30, "ratio": "9:16"},
  "total_duration_sec": 26,
  "tracks": {
    "main_video": [
      {"shot_id": 1, "source": "generated_clip", "start_sec": 0, "duration_sec": 13,
       "transition_out": {"type": "cut", "duration_sec": 0}},
      {"shot_id": 2, "source": "generated_clip", "start_sec": 13, "duration_sec": 13,
       "transition_out": {"type": "cut", "duration_sec": 0}}
    ],
    "pip_video": [],
    "subtitle": [{"text": "钩子", "start_sec": 1, "duration_sec": 2, "style": {"position": "bottom", "size": 48}}],
    "audio": [{"type": "dialogue", "shot_id": 1, "volume": 1}]
  },
  "effects": [],
  "transitions": [{"between_shots": [1, 2], "type": "hard_cut"}],
  "notes": "ok"
}
"""
    plan = parse_compose_plan(raw, _sample_shots())
    assert len(plan["tracks"]["main_video"]) == 2
    assert plan["tracks"]["subtitle"][0]["text"] == "钩子"


def test_generate_compose_plan_mock(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = generate_compose_plan(shots=_sample_shots(), instruction="少转场")
    assert out["mock"] is True
    assert out["compose_plan"]["tracks"]["main_video"]
    assert out["instruction"] == "少转场"


def test_generate_empty_shots() -> None:
    with pytest.raises(HTTPException) as ei:
        generate_compose_plan(shots=[])
    assert ei.value.status_code == 422


def test_export_to_project_dir(tmp_path: Path) -> None:
    plan = build_heuristic_plan(_sample_shots())
    out = export_compose_draft(
        compose_plan=plan,
        shots=_sample_shots(),
        draft_name="demo_export",
        source_url="https://cdn.example.com/src.mp4",
        drafts_dir=str(tmp_path),
    )
    assert "zip_base64" not in out
    draft_dir = Path(out["draft_dir"])
    assert draft_dir.is_dir()
    assert (draft_dir / "compose_plan.json").is_file()
    assert out["drafts_root"] == str(tmp_path.resolve())
    content = build_draft_content(plan, _sample_shots(), draft_name="demo")
    assert content["materials"]["videos"]


def test_resolve_drafts_dir_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIANYING_DRAFTS_DIR", str(tmp_path))
    assert resolve_jianying_drafts_dir() == tmp_path


def test_resolve_jianying_app_env(tmp_path: Path, monkeypatch) -> None:
    from plugins.mxai.content.capcut_draft import resolve_jianying_app

    exe = tmp_path / "JianyingPro.exe"
    exe.write_bytes(b"mz")
    monkeypatch.setenv("JIANYING_APP", str(exe))
    assert resolve_jianying_app() == exe.resolve()


def test_launch_jianying_app_not_found(monkeypatch) -> None:
    from fastapi import HTTPException
    from plugins.mxai.content.capcut_draft import launch_jianying_app

    monkeypatch.delenv("JIANYING_APP", raising=False)
    monkeypatch.delenv("CAPCUT_APP", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(Path("/no-such-jianying-apps")))
    monkeypatch.setenv("ProgramFiles", str(Path("/no-pf")))
    monkeypatch.setenv("ProgramFiles(x86)", str(Path("/no-pf86")))
    try:
        launch_jianying_app()
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail.get("code") == "JIANYING_APP_NOT_FOUND"
