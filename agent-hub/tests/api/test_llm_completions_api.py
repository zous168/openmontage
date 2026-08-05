"""POST /api/plugins/mxai/llm/completions."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_llm_completions_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/llm/completions",
        json={
            "messages": [{"role": "user", "content": "hello hub"}],
            "temperature": 0.2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("source") == "mock"
    assert "hello hub" in (data.get("content") or "")
    assert data.get("usage", {}).get("total_tokens") == 0


def test_llm_completions_accepts_model(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/llm/completions",
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "model": "qwen-plus",
        },
    )
    assert resp.status_code == 200


def test_llm_completions_rejects_empty_messages(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/llm/completions",
        json={"messages": []},
    )
    assert resp.status_code == 422


def test_llm_completions_rejects_invalid_role(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/llm/completions",
        json={"messages": [{"role": "tool", "content": "x"}]},
    )
    assert resp.status_code == 422


def test_llm_completions_accepts_vision_messages(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    resp = mxai_client.post(
        "/api/plugins/mxai/llm/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,abc"},
                        },
                    ],
                }
            ],
            "model": "qwen-vl-max",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("vision") is True
    assert "[vision]" in (data.get("content") or "")
