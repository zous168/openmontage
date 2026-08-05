"""HTTP integration: POST /content/assist SSE."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = "message"
        data_raw = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_raw = line[5:].strip()
        if data_raw:
            out.append((event, json.loads(data_raw)))
    return out


def test_content_assist_sse_mock(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    with mxai_client.stream(
        "POST",
        "/api/plugins/mxai/content/assist",
        json={
            "scene": "agent_soul",
            "format": "markdown",
            "content": "",
            "stream": True,
            "context": {"agent": "wechat_chat"},
        },
        headers={"Accept": "text/event-stream"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in (resp.headers.get("content-type") or "")
        text = resp.read().decode("utf-8")

    events = _parse_sse(text)
    kinds = [e for e, _ in events]
    assert "assist.start" in kinds
    assert "assist.delta" in kinds
    assert "assist.done" in kinds
    done = next(d for e, d in events if e == "assist.done")
    assert done.get("content")
    assert done.get("mode_used") == "generate"
