"""CI/单测禁止 POST 真实 Automan hooks（conftest autouse 门闸）."""

from __future__ import annotations

import httpx
import pytest


def test_autouse_blocks_real_automan_hooks_post() -> None:
    with pytest.raises(RuntimeError, match="禁止打真实 Automan 工作流"):
        with httpx.Client(timeout=1.0, trust_env=False) as client:
            client.post(
                "http://127.0.0.1:8123/api/open/hooks/douyin_comment_collect",
                json={"inputs": {}, "mode": "async"},
            )


def test_fake_client_replacement_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """用例自备 Fake Client（整类替换）时不受门闸影响——与 test_bridge 同模式。"""
    posts: list[str] = []

    class _Fake:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):  # noqa: ANN002
            return False

        def post(self, url, **kwargs):  # noqa: ANN001, ARG002
            posts.append(str(url))
            return type("R", (), {"status_code": 200, "text": "{}", "json": lambda: {}})()

    monkeypatch.setattr(httpx, "Client", _Fake)
    with httpx.Client() as client:
        client.post("http://127.0.0.1:8123/api/open/hooks/douyin_comment_reply", json={})
    assert posts == ["http://127.0.0.1:8123/api/open/hooks/douyin_comment_reply"]
