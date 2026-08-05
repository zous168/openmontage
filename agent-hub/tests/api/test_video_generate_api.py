"""HTTP: POST /content/video-generate（模型无关）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

_DEMO_T2V = "demo-t2v"


def test_video_generate_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-generate",
        json={
            "prompt": "近景产品特写，字幕痛点",
            "model": _DEMO_T2V,
            "duration_sec": 5,
            "aspect_ratio": "9:16",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["model"] == _DEMO_T2V
    assert body["video_url"]
    assert body["duration_sec"] == 5


def test_video_generate_requires_model(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-generate",
        json={
            "prompt": "近景产品特写",
            "duration_sec": 5,
        },
    )
    assert resp.status_code == 422


def test_video_generate_requires_prompt(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-generate",
        json={"prompt": ""},
    )
    assert resp.status_code == 422


def test_video_generate_submit_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-generate/submit",
        json={
            "prompt": "近景产品特写",
            "model": "demo-t2v",
            "duration_sec": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["task_id"] == "mock-task"
    assert body["status"] == "queued"
    assert body["model"] == "demo-t2v"


def test_video_generate_submit_prev_video_mock(mxai_client: TestClient, monkeypatch) -> None:
    """上一镜尾帧参考：提交体带 prev_video_url → i2v + has_reference。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/content/video-generate/submit",
        json={
            "prompt": "续拍产品特写",
            "model": "demo-t2v",
            "duration_sec": 5,
            "prev_video_url": "https://cdn.example.com/shot1.mp4",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["model"] == "demo-i2v"
    assert body["has_reference"] is True
    assert body["reference_source"] == "prev_video"
    assert str(body.get("reference_image") or "").startswith("data:image/")
    assert body.get("prompt")


def test_video_generate_status_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.get(
        "/api/plugins/mxai/content/video-generate/mock-task/status",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["status"] == "completed"
    assert body["video_url"]


def test_gateway_models_generate_purpose(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models._load_catalog",
        lambda: (
            [
                {"model_name": "demo-t2v", "mode": "video_generation", "provider": "demo"},
            ],
            "model_info",
        ),
    )
    resp = mxai_client.get(
        "/api/plugins/mxai/content/gateway-models",
        params={"purpose": "generate"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"][0]["model_name"] == "demo-t2v"
