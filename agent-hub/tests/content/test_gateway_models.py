"""网关模型列表（仿爆款步骤选型）。"""

from __future__ import annotations

import pytest

from plugins.mxai.content.gateway_models import list_gateway_models


def test_list_gateway_models_filter_generate(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                {"model_name": "qwen-vl-max", "mode": "vision", "provider": "dashscope"},
                {"model_name": "wan2.6-t2v", "mode": "video_generation", "provider": "dashscope"},
                {"model_name": "fal-ai/veo3.1", "mode": "video_generation", "provider": "fal"},
            ],
            "model_info",
        ),
    )
    out = list_gateway_models(purpose="generate")
    names = [x["model_name"] for x in out["items"]]
    assert names == ["fal-ai/veo3.1", "wan2.6-t2v"]


def test_list_gateway_models_filter_reverse(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                {"model_name": "gpt-4o", "mode": "vision", "provider": "openai"},
                {"model_name": "qwen-vl-max", "mode": "vision", "provider": "dashscope"},
                {"model_name": "wan2.6-t2v", "mode": "video_generation", "provider": "dashscope"},
            ],
            "model_info",
        ),
    )
    out = list_gateway_models(purpose="reverse")
    names = [x["model_name"] for x in out["items"]]
    assert "qwen-vl-max" in names
    assert "gpt-4o" in names
    assert "wan2.6-t2v" not in names


def test_list_gateway_models_filter_prompt_text_default(monkeypatch) -> None:
    """图文镜头提示词默认：purpose=prompt 只收 CS mode=text；视觉用 mode=vision。"""
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                {"model_name": "MiniMax-M2.7", "mode": "text", "provider": "official"},
                {"model_name": "qwen-vl-max", "mode": "vision", "provider": "dashscope"},
                {"model_name": "gpt-4o", "mode": "vision", "provider": "openai"},
            ],
            "model_info",
        ),
    )
    out = list_gateway_models(purpose="prompt")
    names = [x["model_name"] for x in out["items"]]
    assert names == ["MiniMax-M2.7"]
    vision = list_gateway_models(mode="vision")
    vnames = [x["model_name"] for x in vision["items"]]
    assert "qwen-vl-max" in vnames
    assert "gpt-4o" in vnames
    assert "MiniMax-M2.7" not in vnames


def test_list_gateway_models_trusts_cs_mode_not_name(monkeypatch) -> None:
    """CS 已拆分 text/vision：以 mode 为准，不用模型名猜。"""
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                # 名称像视觉，但 CS 标为 text → 进 prompt/rewrite，不进 reverse
                {"model_name": "gpt-4o-mini", "mode": "text", "provider": "openai"},
                # 名称无 vl，但 CS 标为 vision → 进 reverse / mode=vision
                {"model_name": "custom-mm-01", "mode": "vision", "provider": "custom"},
            ],
            "model_info",
        ),
    )
    rev = list_gateway_models(purpose="reverse")
    prompt = list_gateway_models(purpose="prompt")
    rewrite = list_gateway_models(purpose="rewrite")
    vision = list_gateway_models(mode="vision")
    assert [x["model_name"] for x in rev["items"]] == ["custom-mm-01"]
    assert [x["model_name"] for x in prompt["items"]] == ["gpt-4o-mini"]
    assert [x["model_name"] for x in rewrite["items"]] == ["gpt-4o-mini"]
    assert [x["model_name"] for x in vision["items"]] == ["custom-mm-01"]


def test_list_gateway_models_invalid_mode() -> None:
    with pytest.raises(Exception) as ei:
        list_gateway_models(mode="unknown")
    assert getattr(ei.value, "status_code", None) == 422


def test_normalize_model_info_includes_description() -> None:
    from plugins.mxai.content.gateway_models import _normalize_model_info

    rows = _normalize_model_info(
        [
            {
                "model_name": "wan2.7-i2v",
                "model_info": {
                    "mode": "video_generation",
                    "description": "  万相图生视频  ",
                },
            },
            {
                "model_name": "gpt-4o",
                "model_info": {"mode": "chat"},
            },
        ]
    )
    assert rows[0]["description"] == "万相图生视频"
    assert rows[1]["description"] is None
    assert rows[1]["mode"] == "text"  # 历史 chat → text


def test_normalize_model_info_skips_blocked() -> None:
    from plugins.mxai.content.gateway_models import _normalize_model_info

    rows = _normalize_model_info(
        [
            {
                "model_name": "wan2.6-t2v",
                "blocked": True,
                "model_info": {"mode": "video_generation"},
            },
            {
                "model_name": "wan2.7-i2v",
                "model_info": {"mode": "video_generation", "blocked": True},
            },
            {"model_name": "wan2.7-r2v", "model_info": {"mode": "video_generation"}},
        ]
    )
    assert [r["model_name"] for r in rows] == ["wan2.7-r2v"]


def test_list_gateway_models_excludes_blocked(monkeypatch) -> None:
    from plugins.mxai.content.gateway_models import _normalize_model_info

    def fake_admin() -> list[dict]:
        return _normalize_model_info(
            [
                {
                    "model_name": "wan2.6-t2v",
                    "blocked": True,
                    "model_info": {"mode": "video_generation"},
                },
                {
                    "model_name": "wan2.7-i2v",
                    "model_info": {"mode": "video_generation"},
                },
            ]
        )

    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_admin",
        fake_admin,
    )
    out = list_gateway_models(purpose="generate")
    assert [x["model_name"] for x in out["items"]] == ["wan2.7-i2v"]


def test_load_catalog_intersects_v1_models(monkeypatch) -> None:
    from plugins.mxai.content.gateway_models import _load_catalog

    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_admin",
        lambda: [
            {"model_name": "wan2.6-t2v", "mode": "video_generation", "description": None},
            {"model_name": "wan2.7-i2v", "mode": "video_generation", "description": "可用"},
        ],
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_device_jwt",
        lambda: [],
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_routable_model_names",
        lambda: {"wan2.7-i2v"},
    )
    catalog, source = _load_catalog()
    assert source == "model_info+v1_models"
    assert [m["model_name"] for m in catalog] == ["wan2.7-i2v"]
    assert catalog[0]["description"] == "可用"


def test_load_catalog_merges_device_meta_descriptions(monkeypatch) -> None:
    from plugins.mxai.content.gateway_models import _load_catalog

    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_admin",
        lambda: [],
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_device_jwt",
        lambda: [
            {
                "model_name": "wan2.7-i2v",
                "mode": "video_generation",
                "description": "万相图生视频",
            },
        ],
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_routable_model_names",
        lambda: {"wan2.7-i2v"},
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._fetch_catalog_via_device",
        lambda: [
            {"model_name": "wan2.7-i2v", "mode": "video_generation", "description": None},
        ],
    )
    catalog, source = _load_catalog()
    assert source == "model_info_device+v1_models"
    assert catalog[0]["description"] == "万相图生视频"


def test_merge_catalog_metadata() -> None:
    from plugins.mxai.content.gateway_models import _merge_catalog_metadata

    primary = [{"model_name": "a", "mode": "chat", "description": None}]
    meta = [{"model_name": "a", "mode": "video_generation", "description": "描述 A"}]
    out = _merge_catalog_metadata(primary, meta)
    assert out[0]["description"] == "描述 A"
    assert out[0]["mode"] == "video_generation"


def test_is_blocked_accepts_string_true() -> None:
    from plugins.mxai.content.gateway_models import _is_blocked

    assert _is_blocked({"model_name": "x", "blocked": "true"}) is True


def test_list_gateway_models_filter_voice_clone(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                {
                    "model_name": "cosyvoice-v3-flash",
                    "mode": "audio_speech",
                    "provider": "dashscope",
                },
                {
                    "model_name": "cosyvoice-v3-flash-enroll",
                    "mode": "audio_voice_enrollment",
                    "provider": "dashscope",
                },
            ],
            "model_info",
        ),
    )
    tts = list_gateway_models(purpose="tts")
    clone = list_gateway_models(purpose="voice_clone")
    assert [x["model_name"] for x in tts["items"]] == ["cosyvoice-v3-flash"]
    assert [x["model_name"] for x in clone["items"]] == ["cosyvoice-v3-flash-enroll"]
