"""img-text-generate-shots API 点验。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_api_img_text_generate_shots_mock(mxai_client, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    res = mxai_client.post(
        "/api/plugins/mxai/content/img-text-generate-shots",
        json={
            "params": {
                "product": "玻璃杯子",
                "scene": "factory",
                "video_form": "talking_head",
                "content_style": "ugc",
                "duration_sec": 30,
                "aspect_ratio": "9:16",
                "appear_mode": "walk",
            },
            "model": "qwen-plus",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body.get("shots") or []) == 3
    assert body.get("mock") is True
    assert body.get("params", {}).get("product") == "玻璃杯子"


def test_api_img_text_validate_duration(mxai_client) -> None:
    res = mxai_client.post(
        "/api/plugins/mxai/content/img-text-generate-shots",
        json={
            "params": {
                "product": "x",
                "scene": "factory",
                "video_form": "talking_head",
                "duration_sec": 25,
                "aspect_ratio": "9:16",
                "appear_mode": "walk",
            },
        },
    )
    assert res.status_code == 422
