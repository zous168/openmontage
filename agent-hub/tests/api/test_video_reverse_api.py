"""HTTP: POST /content/video-reverse"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_video_reverse_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-reverse",
        json={"url": "https://cdn.example.com/demo.mp4", "model": "qwen-vl-max"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model"] == "qwen-vl-max"
    assert body["mock"] is True
    assert body["dna_lock"]["fingerprint"]
    assert body["meta"]["segment_sec"] == 13
    assert any(a.get("type") == "product" for a in body["key_assets"])
    assert len(body["shots"]) >= 1
    assert body["shots"][0]["prompt"]
    assert body["shots"][0].get("visual_timeline")


def test_video_reverse_requires_url(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-reverse",
        json={"url": ""},
    )
    assert resp.status_code == 422


def test_video_reverse_accepts_instruction(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-reverse",
        json={
            "url": "https://cdn.example.com/demo.mp4",
            "instruction": "竖屏口播风，字幕大字",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["instruction"] == "竖屏口播风，字幕大字"
    assert "竖屏" in body["shots"][0]["prompt"] or "字幕" in body["shots"][0]["prompt"]
