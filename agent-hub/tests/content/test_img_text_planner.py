"""图文变量 planner 单测。"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from plugins.mxai.content.img_text_planner import generate_img_text_shots, validate_img_text_params


def test_validate_img_text_params_glass_cup() -> None:
    out = validate_img_text_params(
        {
            "product": "玻璃杯子",
            "scene": "factory",
            "video_form": "talking_head",
            "content_style": "ugc",
            "duration_sec": 30,
            "aspect_ratio": "9:16",
            "appear_mode": "walk",
            "refs": [{"id": "img_1", "role": "product", "url": "https://cdn/x.jpg"}],
        },
    )
    assert out["product"] == "玻璃杯子"
    assert out["identity_source"] == "ai_gen"


def test_validate_rejects_bad_duration() -> None:
    with pytest.raises(HTTPException) as ei:
        validate_img_text_params(
            {
                "product": "x",
                "scene": "factory",
                "video_form": "talking_head",
                "duration_sec": 25,
                "aspect_ratio": "9:16",
                "appear_mode": "walk",
            },
        )
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_generate_mock_shots(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    res = await generate_img_text_shots(
        params={
            "product": "玻璃杯子",
            "scene": "factory",
            "video_form": "talking_head",
            "content_style": "ugc",
            "duration_sec": 30,
            "aspect_ratio": "9:16",
            "appear_mode": "walk",
        },
        model="mock-vision",
    )
    assert len(res["shots"]) == 3
    assert res["mock"] is True
    assert res["history_id"]


@pytest.mark.asyncio
async def test_generate_real_vision_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MXAI_MOCK", raising=False)

    analysis = json.dumps(
        {
            "dna_lock": {
                "character": "女工人口播",
                "wardrobe": "深蓝工装",
                "scene": "玻璃厂车间",
                "lighting": "顶灯+侧窗",
                "fingerprint": "glass-factory",
            },
            "sections": [
                {
                    "key": "environment",
                    "title": "环境",
                    "fields": [{"key": "setting", "label": "场景", "type": "text", "value": "车间"}],
                }
            ],
            "source_copy": {
                "full_script": "钩子\n卖点\nCTA",
                "hook": "钩子",
                "cta": "CTA",
                "summary": "玻璃杯工厂口播",
            },
            "meta": {"total_duration_sec": 30, "segment_sec": 10, "segment_count": 3},
            "shots": [
                {
                    "id": "1",
                    "title": "镜1",
                    "duration_sec": 10,
                    "copy": "钩子",
                    "prompt": "UGC handheld glass cup shot 1, real-time physics, 9:16",
                    "shot_type": "talking_head",
                    "camera_move": "handheld_follow",
                    "transition_in": "fade_in",
                    "gen_mode": "t2v",
                },
                {
                    "id": "2",
                    "title": "镜2",
                    "duration_sec": 10,
                    "copy": "卖点",
                    "prompt": "UGC handheld glass cup shot 2, real-time physics, 9:16",
                    "gen_mode": "t2v",
                },
                {
                    "id": "3",
                    "title": "镜3",
                    "duration_sec": 10,
                    "copy": "CTA",
                    "prompt": "UGC handheld glass cup shot 3, real-time physics, 9:16",
                    "gen_mode": "t2v",
                },
            ],
        },
        ensure_ascii=False,
    )

    class _Resp:
        pass

    async def fake_llm(**kwargs):
        assert kwargs.get("task") == "vision"
        assert kwargs.get("model") == "qwen-vl-max"
        return _Resp()

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_llm)
    monkeypatch.setattr(
        "agent.auxiliary_client.extract_content_or_reasoning",
        lambda _r: analysis,
    )

    res = await generate_img_text_shots(
        params={
            "product": "玻璃杯子",
            "scene": "factory",
            "video_form": "talking_head",
            "content_style": "ugc",
            "duration_sec": 30,
            "aspect_ratio": "9:16",
            "appear_mode": "walk",
            "refs": [{"id": "img_1", "role": "product", "url": "https://cdn.example/p.jpg"}],
        },
        model="qwen-vl-max",
    )
    assert res["mock"] is False
    assert len(res["shots"]) == 3
    assert res["sections"][0]["key"] == "environment"
    assert "glass" in (res["shots"][0].get("prompt") or "").lower()


@pytest.mark.asyncio
async def test_generate_no_refs_auto_default_text_model(monkeypatch) -> None:
    """无参考图：可不传 model，自动取 purpose=prompt 默认文本模型。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models.list_gateway_models",
        lambda **_kw: {"items": [{"model_name": "auto-text-01", "mode": "text"}]},
    )
    res = await generate_img_text_shots(
        params={
            "product": "x",
            "scene": "factory",
            "video_form": "talking_head",
            "duration_sec": 30,
            "aspect_ratio": "9:16",
            "appear_mode": "walk",
        },
        model="",
    )
    assert res["model"] == "auto-text-01"


@pytest.mark.asyncio
async def test_generate_with_refs_requires_vision_model(monkeypatch) -> None:
    monkeypatch.delenv("MXAI_MOCK", raising=False)
    with pytest.raises(HTTPException) as ei:
        await generate_img_text_shots(
            params={
                "product": "x",
                "scene": "factory",
                "video_form": "talking_head",
                "duration_sec": 30,
                "aspect_ratio": "9:16",
                "appear_mode": "walk",
                "refs": [{"id": "r1", "role": "product", "url": "https://cdn.example/p.jpg"}],
            },
            model="",
        )
    assert ei.value.status_code == 422
    assert "素材参考" in str(ei.value.detail)
