"""分镜视频生成：mock / 网关 / 直连 + 首帧参考（模型无关）。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from plugins.mxai.content.video_generate import (
    generate_video_clip,
    poll_video_status,
    submit_video_clip,
)

# 测试用别名：只验证 t2v→i2v 规则，不绑定具体厂商型号
_T2V = "demo-t2v"
_I2V = "demo-i2v"


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_mock_mode_requires_model(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = await generate_video_clip(
        prompt="近景口播，暖色客厅",
        duration_sec=13,
        aspect_ratio="9:16",
        model=_T2V,
    )
    assert out["mock"] is True
    assert out["model"] == _T2V
    assert out["duration_sec"] == 13
    assert out["video_url"]
    assert "720*1280" in out["size"]


@pytest.mark.asyncio
async def test_requires_model(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    with pytest.raises(HTTPException) as ei:
        await generate_video_clip(prompt="近景口播", duration_sec=5)
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "MODEL_REQUIRED"


@pytest.mark.asyncio
async def test_requires_prompt(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    with pytest.raises(HTTPException) as ei:
        await generate_video_clip(prompt="  ")
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_submit_returns_task_id_immediately(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    sub = await submit_video_clip(prompt="近景口播", duration_sec=5, model=_T2V)
    assert sub["mock"] is True
    assert sub["task_id"] == "mock-task"
    assert sub["status"] == "queued"
    assert sub["model"] == _T2V
    st = await poll_video_status(sub["task_id"])
    assert st["status"] == "completed"
    assert st["video_url"]


@pytest.mark.asyncio
async def test_gateway_submit_and_poll_once(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.delenv("WAN_T2V_DIRECT", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    calls: list[str] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append("post")
            assert url.endswith("/v1/videos")
            assert json["model"] == _T2V
            assert json["seconds"] == "5"
            return _Resp(200, {"id": "vid-abc", "status": "queued"})

        async def get(self, url, headers=None):
            calls.append("get")
            assert "/v1/videos/vid-abc" in url
            if calls.count("get") == 1:
                return _Resp(200, {"id": "vid-abc", "status": "in_progress"})
            return _Resp(
                200,
                {
                    "id": "vid-abc",
                    "status": "completed",
                    "usage": {"video_url": "https://cdn.example.com/o.mp4"},
                },
            )

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)

    sub = await submit_video_clip(prompt="近景口播测试足够长", duration_sec=5, model=_T2V)
    assert sub["mock"] is False
    assert sub["task_id"] == "vid-abc"
    assert sub["status"] == "queued"
    assert calls == ["post"]

    st = await poll_video_status("vid-abc")
    assert st["status"] == "in_progress"
    assert calls.count("get") == 1

    st2 = await poll_video_status("vid-abc")
    assert st2["status"] == "completed"
    assert st2["video_url"] == "https://cdn.example.com/o.mp4"
    assert calls.count("get") == 2


@pytest.mark.asyncio
async def test_gateway_generate_polls_to_completion(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.delenv("WAN_T2V_DIRECT", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    calls: list[str] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append("post")
            assert url.endswith("/v1/videos")
            assert json["model"] == _T2V
            return _Resp(200, {"id": "vid-abc", "status": "queued"})

        async def get(self, url, headers=None):
            calls.append("get")
            if calls.count("get") == 1:
                return _Resp(200, {"id": "vid-abc", "status": "in_progress"})
            return _Resp(
                200,
                {
                    "id": "vid-abc",
                    "status": "completed",
                    "usage": {"video_url": "https://cdn.example.com/o.mp4"},
                },
            )

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)
    monkeypatch.setattr("plugins.mxai.content.video_generate.POLL_INTERVAL_SEC", 0.01)

    out = await generate_video_clip(prompt="近景口播测试足够长", duration_sec=5, model=_T2V)
    assert out["mock"] is False
    assert out["task_id"] == "vid-abc"
    assert out["video_url"] == "https://cdn.example.com/o.mp4"
    assert "post" in calls and calls.count("get") >= 2


@pytest.mark.asyncio
async def test_direct_submit_and_poll(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("VIDEO_GEN_DIRECT", "1")
    monkeypatch.setenv("WAN_T2V_DIRECT", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_VIDEO_BASE_URL", "https://dashscope.example.com/api/v1")

    calls: list[str] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append("post")
            assert "video-synthesis" in url
            assert headers.get("X-DashScope-Async") == "enable"
            assert json["model"] == _T2V
            return _Resp(200, {"output": {"task_id": "task-abc"}})

        async def get(self, url, headers=None):
            calls.append("get")
            assert url.endswith("/tasks/task-abc")
            if calls.count("get") == 1:
                return _Resp(200, {"output": {"task_status": "RUNNING"}})
            return _Resp(
                200,
                {"output": {"task_status": "SUCCEEDED", "video_url": "https://cdn.example.com/o.mp4"}},
            )

    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)
    monkeypatch.setattr("plugins.mxai.content.video_generate.POLL_INTERVAL_SEC", 0.01)

    out = await generate_video_clip(prompt="近景口播测试足够长", duration_sec=5, model=_T2V)
    assert out["mock"] is False
    assert out["task_id"] == "task-abc"
    assert out["video_url"] == "https://cdn.example.com/o.mp4"


@pytest.mark.asyncio
async def test_direct_missing_api_key(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("VIDEO_GEN_DIRECT", "1")
    monkeypatch.setenv("WAN_T2V_DIRECT", "1")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(HTTPException) as ei:
        await generate_video_clip(prompt="测试提示词", model=_T2V)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_mock_prev_video_keeps_selected_model(monkeypatch) -> None:
    """有上一镜成片时仍用所选 model，并带首帧参考。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    sub = await submit_video_clip(
        prompt="续拍口播，暖色客厅",
        model=_I2V,
        prev_video_url="https://cdn.example.com/shot1.mp4",
    )
    assert sub["model"] == _I2V
    assert sub["has_reference"] is True
    assert "首帧" in (sub.get("prompt") or "")
    assert sub["reference_source"] == "prev_video"
    assert sub["prev_video_url"] == "https://cdn.example.com/shot1.mp4"
    assert str(sub.get("reference_image") or "").startswith("data:image/")
    assert sub.get("prompt")


@pytest.mark.asyncio
async def test_gateway_prev_video_sends_public_img_url(monkeypatch) -> None:
    """网关 Videos：上一镜尾帧上传公网 URL，仅走 extra_body.img_url（无 input_reference）。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.delenv("WAN_T2V_DIRECT", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    posted: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            posted["url"] = url
            posted["json"] = json
            return _Resp(200, {"id": "vid-i2v", "status": "queued"})

        async def get(self, url, headers=None):
            return _Resp(
                200,
                {
                    "id": "vid-i2v",
                    "status": "completed",
                    "usage": {"video_url": "https://cdn.example.com/o2.mp4"},
                },
            )

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)
    monkeypatch.setattr(
        "plugins.mxai.content.video_frame.extract_last_frame_data_url",
        lambda url: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAg",
    )
    monkeypatch.setattr(
        "plugins.mxai.content.ref_upload.ensure_public_image_url",
        lambda ref: "https://oss.example.com/frame.jpg",
    )

    sub = await submit_video_clip(
        prompt="续拍口播测试足够长",
        model=_I2V,
        duration_sec=5,
        prev_video_url="https://cdn.example.com/prev.mp4",
    )
    assert sub["task_id"] == "vid-i2v"
    assert sub["model"] == _I2V
    assert sub["has_reference"] is True
    body = posted["json"]
    assert body["model"] == _I2V
    assert "input_reference" not in body
    assert (body.get("extra_body") or {}).get("img_url") == "https://oss.example.com/frame.jpg"


@pytest.mark.asyncio
async def test_direct_prev_video_sends_img_url(monkeypatch) -> None:
    """直连合成接口：上一镜尾帧写入 input.img_url，模型用所选 i2v。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("VIDEO_GEN_DIRECT", "1")
    monkeypatch.setenv("WAN_T2V_DIRECT", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_VIDEO_BASE_URL", "https://dashscope.example.com/api/v1")

    posted: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            posted["url"] = url
            posted["json"] = json
            return _Resp(200, {"output": {"task_id": "task-i2v"}})

        async def get(self, url, headers=None):
            return _Resp(
                200,
                {
                    "output": {
                        "task_status": "SUCCEEDED",
                        "video_url": "https://cdn.example.com/o2.mp4",
                    }
                },
            )

    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)
    monkeypatch.setattr(
        "plugins.mxai.content.video_frame.extract_last_frame_data_url",
        lambda url: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAg",
    )

    sub = await submit_video_clip(
        prompt="续拍口播测试足够长",
        model=_I2V,
        duration_sec=5,
        prev_video_url="https://cdn.example.com/prev.mp4",
    )
    assert sub["task_id"] == "task-i2v"
    assert sub["model"] == _I2V
    body = posted["json"]
    assert "video-synthesis" in posted["url"]
    assert body["model"] == _I2V
    assert str(body["input"].get("img_url") or "").startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_direct_wan27_i2v_sends_media(monkeypatch) -> None:
    """wan2.7-i2v 直连：参考图写入 input.media，分辨率用 resolution。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("VIDEO_GEN_DIRECT", "1")
    monkeypatch.setenv("WAN_T2V_DIRECT", "1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_VIDEO_BASE_URL", "https://dashscope.example.com/api/v1")

    posted: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            posted["json"] = json
            return _Resp(200, {"output": {"task_id": "task-wan27"}})

        async def get(self, url, headers=None):
            return _Resp(200, {"output": {"task_status": "PENDING"}})

    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)
    monkeypatch.setattr(
        "plugins.mxai.content.video_frame.extract_last_frame_data_url",
        lambda url: "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAg",
    )

    sub = await submit_video_clip(
        prompt="续拍口播测试足够长",
        model="wan2.7-i2v",
        duration_sec=8,
        prev_video_url="https://cdn.example.com/prev.mp4",
    )
    assert sub["model"] == "wan2.7-i2v"
    body = posted["json"]
    assert body["model"] == "wan2.7-i2v"
    assert "img_url" not in body["input"]
    media = body["input"].get("media") or []
    assert len(media) == 1
    assert media[0]["type"] == "first_frame"
    assert str(media[0]["url"]).startswith("data:image/jpeg;base64,")
    assert body["parameters"]["resolution"] == "720P"
    assert "size" not in body["parameters"]


@pytest.mark.asyncio
async def test_gateway_explicit_img_url_uses_selected_i2v(monkeypatch) -> None:
    """显式 http 参考图 + 所选 i2v：仅 extra_body.img_url，无 input_reference。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.delenv("WAN_T2V_DIRECT", raising=False)

    posted: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            posted["json"] = json
            return _Resp(200, {"id": "vid-ref", "status": "queued"})

        async def get(self, url, headers=None):
            return _Resp(200, {"id": "vid-ref", "status": "queued"})

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)

    sub = await submit_video_clip(
        prompt="人物特写口播足够长",
        model=_I2V,
        img_url="https://cdn.example.com/character.png",
    )
    assert sub["model"] == _I2V
    assert posted["json"]["model"] == _I2V
    assert "input_reference" not in posted["json"]
    assert (posted["json"].get("extra_body") or {}).get("img_url") == (
        "https://cdn.example.com/character.png"
    )


def test_canonical_video_task_id_unwraps_litellm() -> None:
    from plugins.mxai.content.video_generate import canonical_video_task_id

    enc = (
        "video_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpkb3ViYW8t"
        "dmlkZW8tcnBhLWkydjt2aWRlb19pZDpycGF2aWRfZGE5MjhlMDlhMmYyNDlmZDgyNjA="
    )
    assert canonical_video_task_id(enc) == "rpavid_da928e09a2f249fd8260"
    assert canonical_video_task_id("rpavid_x") == "rpavid_x"


@pytest.mark.asyncio
async def test_rpa_submit_returns_split_ids(monkeypatch) -> None:
    """RPA：submit 返回 gateway_video_id（LiteLLM）与 task_id（rpavid）分离。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)

    enc = (
        "video_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpkb3ViYW8t"
        "dmlkZW8tcnBhLXQydjt2aWRlb19pZDpycGF2aWRfYWJjZGVm"
    )

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return _Resp(200, {"id": enc, "status": "queued"})

        async def get(self, url, headers=None):
            raise AssertionError("submit should not GET")

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)

    sub = await submit_video_clip(prompt="近景口播测试足够长", duration_sec=5, model=_T2V)
    assert sub["gateway_video_id"] == enc
    assert sub["task_id"] == "rpavid_abcdef"
    assert sub["task_id"] != sub["gateway_video_id"]


@pytest.mark.asyncio
async def test_poll_rejects_bare_rpavid_without_litellm_id(monkeypatch) -> None:
    """不得用 rpavid_* 直接打 LiteLLM GET。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )

    with pytest.raises(HTTPException) as ei:
        await poll_video_status("rpavid_orphan")
    assert ei.value.detail["code"] == "VIDEO_POLL_ID_MISSING"


@pytest.mark.asyncio
async def test_rpa_poll_uses_litellm_video_id_in_url(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)

    enc = (
        "video_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpkb3ViYW8t"
        "dmlkZW8tcnBhLXQydjt2aWRlb19pZDpycGF2aWRfYWJjZGVm"
    )
    get_urls: list[str] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            get_urls.append(url)
            return _Resp(200, {"id": enc, "status": "queued", "progress": 0})

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)

    await poll_video_status(enc)
    assert len(get_urls) == 1
    assert enc in get_urls[0]
    assert "rpavid_" not in get_urls[0]


@pytest.mark.asyncio
async def test_gateway_previous_video_id_in_extra_body(monkeypatch) -> None:
    """镜链续写：previous_video_id 写入 extra_body（通用，不按模型名分支）。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)

    posted: dict = {}

    class _Resp:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data
            self.content = b"{}"

        def json(self):
            return self._data

        @property
        def text(self):
            return ""

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            posted["json"] = json
            return _Resp(200, {"id": "vid-chain", "status": "queued"})

        async def get(self, url, headers=None):
            return _Resp(200, {"id": "vid-chain", "status": "queued"})

    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: ("https://gw.example.com", "jwt-test"),
    )
    monkeypatch.setattr("plugins.mxai.content.video_generate.httpx.AsyncClient", _Client)

    # 历史镜头可能存了 LiteLLM 编码 id，提交续写前须还原为 rpavid_*
    enc_prev = (
        "video_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpkb3ViYW8t"
        "dmlkZW8tcnBhLWkydjt2aWRlb19pZDpycGF2aWRfcHJldjE="
    )
    sub = await submit_video_clip(
        prompt="第二镜口播测试足够长",
        model=_T2V,
        duration_sec=5,
        previous_video_id=enc_prev,
    )
    assert sub["task_id"] == "vid-chain"
    assert (posted["json"].get("extra_body") or {}).get("previous_video_id") == (
        "rpavid_prev1"
    )


@pytest.mark.asyncio
async def test_wan27_i2v_requires_reference(monkeypatch) -> None:
    """wan2.7-i2v 无首帧时不应打到网关，直接 422。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)

    with pytest.raises(HTTPException) as ei:
        await submit_video_clip(
            prompt="人物特写口播足够长",
            model="wan2.7-i2v",
            duration_sec=5,
        )
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "REFERENCE_REQUIRED"
