"""智能创作生成历史（JSON 落盘）。"""

from __future__ import annotations

from plugins.mxai.content.create_history import (
    KIND_IMG_TEXT,
    KIND_VIRAL_CLONE,
    compose_history_title,
    delete_history,
    get_history,
    list_history,
    save_history,
)
from plugins.mxai.content.checkpoint import is_stage_id


def test_compose_history_title_includes_short_id() -> None:
    sid = "3dffb707-e384-4597-89c0-d7bba63adeeb"
    title = compose_history_title(
        kind=KIND_IMG_TEXT,
        params={"product": "玻璃杯"},
        shots=[{"title": "整段反推"}],
        session_id=sid,
    )
    assert title.startswith("玻璃杯")
    assert title.endswith("3dffb707")


def test_save_list_get_reuse(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/a.mp4",
        model="qwen-vl-max",
        shots=[
            {"title": "开场", "duration_sec": 3, "prompt": "产品特写痛点字幕"},
            {"title": "对比", "duration_sec": 4, "prompt": "前后分屏效果展示"},
        ],
    )
    assert saved["id"]
    assert saved["shot_count"] == 2
    assert saved["id_short"] == saved["id"].replace("-", "")[:8]
    assert saved["id_short"] in saved["title"]

    listed = list_history(KIND_VIRAL_CLONE)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == saved["id"]
    assert listed["items"][0]["id_short"] == saved["id_short"]
    assert "shots" not in listed["items"][0]

    detail = get_history(KIND_VIRAL_CLONE, saved["id"])
    assert len(detail["shots"]) == 2
    assert detail["shots"][0]["prompt"].startswith("产品特写")

    # 更新同一条，并合并 step_raw
    updated = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=saved["id"],
        source_url="https://cdn.example.com/a.mp4",
        model="qwen-vl-max",
        shots=[{"title": "新开场", "duration_sec": 2, "prompt": "改写后的提示词足够长"}],
        step_raw={"reverse": {"raw": "model-original", "mock": True}},
    )
    assert updated["id"] == saved["id"]
    assert updated["shot_count"] == 1
    assert (updated.get("step_raw") or {})["reverse"]["raw"] == "model-original"

    with_gen = save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=saved["id"],
        source_url="https://cdn.example.com/a.mp4",
        shots=[{"title": "新开场", "duration_sec": 2, "prompt": "改写后的提示词足够长"}],
        step_raw={"generate": {"clips": [{"id": 1, "url": "https://x/a.mp4"}]}},
    )
    # 单轨：产物合并进 step_raw（reverse 保留 + generate 追加）
    assert (with_gen.get("step_raw") or {})["reverse"]["raw"] == "model-original"
    assert (with_gen.get("step_raw") or {})["generate"]["clips"][0]["id"] == 1

    listed2 = list_history(KIND_VIRAL_CLONE)
    assert "generate" in listed2["items"][0]["step_raw_keys"]
    assert "reverse" in listed2["items"][0]["step_raw_keys"]

    delete_history(KIND_VIRAL_CLONE, saved["id"])
    assert list_history(KIND_VIRAL_CLONE)["total"] == 0


def test_save_shot_preserves_generated_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/a.mp4",
        model="wan2.6-t2v",
        shots=[
            {
                "title": "镜头 1",
                "duration_sec": 5,
                "prompt": "产品特写痛点字幕足够长",
                "preview_url": "https://cdn.example.com/out.mp4",
                "task_id": "vid-abc",
                "mock": False,
            },
        ],
    )
    detail = get_history(KIND_VIRAL_CLONE, saved["id"])
    shot = detail["shots"][0]
    assert shot["preview_url"] == "https://cdn.example.com/out.mp4"
    assert shot["task_id"] == "vid-abc"
    assert shot["mock"] is False


def test_save_shot_preserves_tts_media(tmp_path, monkeypatch) -> None:
    """配音 tts_url/tts_path 落盘，恢复后可显示「分镜配音试听」。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/a.mp4",
        model="IndexTTS-2",
        shots=[
            {
                "title": "镜头 1",
                "duration_sec": 5,
                "prompt": "产品特写旁白足够长",
                "tts_url": "/content/voice-media/tts_demo.mp3",
                "tts_path": str(tmp_path / "tts_demo.mp3"),
            },
        ],
    )
    detail = get_history(KIND_VIRAL_CLONE, saved["id"])
    shot = detail["shots"][0]
    assert shot["tts_url"] == "/content/voice-media/tts_demo.mp3"
    assert shot["tts_path"].endswith("tts_demo.mp3")


def test_product_replace_kind_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind="product_replace",
        source_url="https://cdn.example.com/original.mp4",
        shots=[{"title": "镜1", "duration_sec": 13, "prompt": "框架锁定产品替换足够长的提示词"}],
        params={"segment_sec": 13, "refs": [{"id": "p1", "role": "product", "url": "https://cdn/x.jpg"}]},
    )
    assert saved["kind"] == "product_replace"
    detail = get_history("product_replace", saved["id"])
    assert detail["params"]["segment_sec"] == 13
    assert len(detail["params"]["refs"]) == 1


def test_img_text_kind_params_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind="img_text",
        params={"product": "玻璃杯子", "duration_sec": 30, "aspect": "9:16"},
        shots=[],
    )
    assert saved["kind"] == "img_text"
    detail = get_history("img_text", saved["id"])
    assert detail["params"]["product"] == "玻璃杯子"
