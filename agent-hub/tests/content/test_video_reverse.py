"""仿爆款视频反推：结构化解析 + mock + 工具调用契约。"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from plugins.mxai.content.video_reverse import (
    DEFAULT_MODEL,
    SEGMENT_SEC,
    parse_reverse_payload,
    reverse_video_to_shots,
)


def test_parse_shots_from_clean_json() -> None:
    raw = json.dumps(
        {
            "shots": [
                {"id": 1, "title": "开场", "duration_sec": 3, "prompt": "产品特写，字幕痛点"},
                {"id": 2, "title": "对比", "duration_sec": 4, "prompt": "前后分屏展示效果"},
            ]
        },
        ensure_ascii=False,
    )
    payload = parse_reverse_payload(raw, max_shots=6)
    shots = payload["shots"]
    assert len(shots) == 2
    assert shots[0]["title"] == "开场"
    assert shots[0]["duration_sec"] == 3
    assert "产品特写" in shots[0]["prompt"]


def test_parse_structured_payload() -> None:
    raw = json.dumps(
        {
            "dna_lock": {
                "character": "青年男，短发",
                "wardrobe": "黑T恤",
                "scene": "街头夜景",
                "lighting": "霓虹侧光",
                "fingerprint": "neon-street-black-tee",
            },
            "key_assets": [
                {
                    "id": "char_1",
                    "type": "character",
                    "name": "男主",
                    "original_desc": "青年男短发黑T",
                    "appearance": "青年男，短发，黑T恤",
                },
                {
                    "id": "prod_1",
                    "type": "product",
                    "name": "能量饮料",
                    "original_desc": "蓝罐饮料",
                    "appearance": "蓝色拉环罐，高15cm",
                },
            ],
            "source_copy": {
                "full_script": "你是不是也试过十几种方法？今天这一罐就见效。",
                "on_screen_text": "痛点字幕 @00:02",
                "hook": "你是不是也试过十几种方法？",
                "cta": "评论区扣1",
                "summary": "痛点+产品+引导",
            },
            "meta": {"total_duration_sec": 26, "segment_sec": 13, "segment_count": 2},
            "shots": [
                {
                    "id": 1,
                    "title": "段1",
                    "duration_sec": 13,
                    "time_range": "00:00-00:13",
                    "inherit_dna": False,
                    "copy": "你是不是也试过十几种方法？",
                    "background": {
                        "setting": "街头夜景霓虹侧光",
                        "layers": "前景人物；背景虚化霓虹",
                        "props": "蓝罐饮料",
                        "lighting": "霓虹侧光",
                        "palette": "蓝紫冷调",
                    },
                    "visual_timeline": [
                        {
                            "t_start": "00:00",
                            "t_end": "00:05",
                            "camera": "中景",
                            "action": "行走前移",
                            "objects": "手机占屏宽10%",
                        }
                    ],
                    "editing": "手持微晃",
                    "audio": {
                        "dialogue_timeline": "00:02 你好",
                        "micro_acoustics": "吸气",
                        "rir": "户外开放",
                    },
                    "prompt": "",
                },
                {
                    "id": 2,
                    "title": "段2",
                    "duration_sec": 13,
                    "time_range": "00:13-00:26",
                    "inherit_dna": True,
                    "visual_timeline": [
                        {
                            "t_start": "00:13",
                            "t_end": "00:20",
                            "camera": "近景",
                            "action": "转身说话",
                        }
                    ],
                    "prompt": "显式完整提示词内容足够长",
                },
            ],
        },
        ensure_ascii=False,
    )
    parsed = parse_reverse_payload(raw, max_shots=6)
    assert parsed["dna_lock"]["fingerprint"] == "neon-street-black-tee"
    assert parsed["source_copy"]["hook"] == "你是不是也试过十几种方法？"
    assert parsed["meta"]["segment_sec"] == SEGMENT_SEC
    assert len(parsed["key_assets"]) == 2
    assert parsed["key_assets"][0]["type"] == "character"
    assert parsed["key_assets"][1]["name"] == "能量饮料"
    assert len(parsed["shots"]) == 2
    assert parsed["shots"][0]["inherit_dna"] is False
    assert parsed["shots"][1]["inherit_dna"] is True
    assert "DNA" in parsed["shots"][0]["prompt"] or "dna" in parsed["shots"][0]["prompt"].lower()
    assert "行走前移" in parsed["shots"][0]["prompt"]
    assert parsed["shots"][0]["copy"] == "你是不是也试过十几种方法？"
    assert parsed["shots"][0]["background"]["setting"] == "街头夜景霓虹侧光"
    assert "该镜口播/字幕原文" in parsed["shots"][0]["prompt"]
    assert "镜头背景" in parsed["shots"][0]["prompt"]
    assert parsed["shots"][1]["prompt"].startswith("显式")


def test_parse_shots_from_fenced_json() -> None:
    raw = """以下是结果：
```json
{"shots":[{"id":1,"title":"A","duration_sec":5,"prompt":"镜头A描述内容足够长"}]}
```
"""
    payload = parse_reverse_payload(raw, max_shots=6)
    shots = payload["shots"]
    assert len(shots) == 1
    assert shots[0]["title"] == "A"


def test_parse_shots_fallback_plain_text() -> None:
    payload = parse_reverse_payload("整段画面：主角跑步穿越城市夜景", max_shots=6)
    shots = payload["shots"]
    assert len(shots) == 1
    assert shots[0]["title"] == "整段反推"
    assert "跑步" in shots[0]["prompt"]


@pytest.mark.asyncio
async def test_reverse_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = await reverse_video_to_shots(url="https://cdn.example.com/a.mp4", model="qwen-vl-max")
    assert out["mock"] is True
    assert out["model"] == "qwen-vl-max"
    assert out["source_copy"]["hook"]
    assert out["dna_lock"]["fingerprint"]
    assert out["meta"]["segment_sec"] == SEGMENT_SEC
    assert any(a.get("type") == "character" for a in out["key_assets"])
    assert any(a.get("type") == "product" for a in out["key_assets"])
    assert len(out["shots"]) >= 1
    assert all(s.get("prompt") for s in out["shots"])
    assert out["shots"][0].get("copy")
    assert out["shots"][0].get("background", {}).get("setting")
    assert out["shots"][0].get("visual_timeline")


@pytest.mark.asyncio
async def test_reverse_calls_video_analyze(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    called: dict = {}

    async def _fake_tool(video_url, user_prompt, model=None):
        called["url"] = video_url
        called["model"] = model
        called["prompt"] = user_prompt
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "dna_lock": {
                            "character": "测试角色",
                            "wardrobe": "红衣",
                            "scene": "室内",
                            "lighting": "顶光",
                            "fingerprint": "test-fp",
                        },
                        "meta": {"total_duration_sec": 13, "segment_sec": 13, "segment_count": 1},
                        "shots": [
                            {
                                "id": 1,
                                "title": "镜1",
                                "duration_sec": 13,
                                "time_range": "00:00-00:13",
                                "inherit_dna": False,
                                "visual_timeline": [
                                    {
                                        "t_start": "00:00",
                                        "t_end": "00:13",
                                        "camera": "中景",
                                        "action": "站立口播微动态填充",
                                    }
                                ],
                                "audio": {"dialogue_timeline": "你好世界"},
                                "prompt": "测试提示词足够长用于校验",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("tools.vision_tools.video_analyze_tool", _fake_tool, raising=False)
    import tools.vision_tools as vt

    monkeypatch.setattr(vt, "video_analyze_tool", _fake_tool)

    out = await reverse_video_to_shots(
        url="https://cdn.example.com/clip.mp4",
        model=DEFAULT_MODEL,
        max_shots=6,
        instruction="偏电影感，禁止出现品牌 Logo",
    )
    assert called["url"] == "https://cdn.example.com/clip.mp4"
    assert called["model"] == "qwen-vl-max"
    assert "DNA" in called["prompt"] or "dna" in called["prompt"].lower()
    assert "JSON Schema" in called["prompt"] or "shots" in called["prompt"]
    assert "用户额外要求" in called["prompt"]
    assert "电影感" in called["prompt"]
    assert out["mock"] is False
    assert out["dna_lock"]["fingerprint"] == "test-fp"
    assert out["instruction"] == "偏电影感，禁止出现品牌 Logo"
    assert len(out["shots"]) == 1


@pytest.mark.asyncio
async def test_reverse_resolves_douyin_url_before_analyze(monkeypatch) -> None:
    """抖音分享链接须先解析为直链；source_url 仍保留原链接。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    douyin = "https://v.douyin.com/iAbc123/"
    direct = "https://aweme.snssdk.com/aweme/v1/play/?video_id=x&ratio=1080p"
    called: dict = {}

    async def _fake_resolve(url: str) -> str:
        called["resolve_in"] = url
        return direct

    async def _fake_tool(video_url, user_prompt, model=None):
        called["url"] = video_url
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "dna_lock": {
                            "character": "测试角色",
                            "wardrobe": "红衣",
                            "scene": "室内",
                            "lighting": "顶光",
                            "fingerprint": "dy-fp",
                        },
                        "meta": {"total_duration_sec": 13, "segment_sec": 13, "segment_count": 1},
                        "shots": [
                            {
                                "id": 1,
                                "title": "镜1",
                                "duration_sec": 13,
                                "time_range": "00:00-00:13",
                                "inherit_dna": False,
                                "visual_timeline": [
                                    {
                                        "t_start": "00:00",
                                        "t_end": "00:13",
                                        "camera": "中景",
                                        "action": "口播",
                                    }
                                ],
                                "audio": {"dialogue_timeline": "你好"},
                                "prompt": "抖音原片反推提示词足够长",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.resolve_douyin_direct_url",
        _fake_resolve,
    )
    import tools.vision_tools as vt

    monkeypatch.setattr(vt, "video_analyze_tool", _fake_tool)

    out = await reverse_video_to_shots(url=douyin, model=DEFAULT_MODEL, max_shots=6)
    assert called["resolve_in"] == douyin
    assert called["url"] == direct
    assert out["source_url"] == douyin
    assert out["resolved_url"] == direct
    assert len(out["shots"]) == 1


@pytest.mark.asyncio
async def test_reverse_resolves_douyin_share_paste(monkeypatch) -> None:
    """整段抖音分享文案须抽出短链再解析；source_url 存干净链接。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    paste = (
        "8- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 "
        "https://v.douyin.com/cZrGrGkT5VI/ 7@8.com :1pm"
    )
    clean = "https://v.douyin.com/cZrGrGkT5VI/"
    direct = "https://aweme.snssdk.com/aweme/v1/play/?video_id=x&ratio=1080p"
    called: dict = {}

    async def _fake_resolve(url: str) -> str:
        called["resolve_in"] = url
        return direct

    async def _fake_tool(video_url, user_prompt, model=None):
        called["url"] = video_url
        return json.dumps(
            {
                "success": True,
                "analysis": json.dumps(
                    {
                        "dna_lock": {
                            "character": "测试角色",
                            "wardrobe": "红衣",
                            "scene": "室内",
                            "lighting": "顶光",
                            "fingerprint": "dy-paste",
                        },
                        "meta": {"total_duration_sec": 13, "segment_sec": 13, "segment_count": 1},
                        "shots": [
                            {
                                "id": 1,
                                "title": "镜1",
                                "duration_sec": 13,
                                "time_range": "00:00-00:13",
                                "inherit_dna": False,
                                "visual_timeline": [
                                    {
                                        "t_start": "00:00",
                                        "t_end": "00:13",
                                        "camera": "中景",
                                        "action": "口播",
                                    }
                                ],
                                "audio": {"dialogue_timeline": "你好"},
                                "prompt": "分享文案反推提示词足够长",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.resolve_douyin_direct_url",
        _fake_resolve,
    )
    import tools.vision_tools as vt

    monkeypatch.setattr(vt, "video_analyze_tool", _fake_tool)

    out = await reverse_video_to_shots(url=paste, model=DEFAULT_MODEL, max_shots=6)
    assert called["resolve_in"] == clean
    assert called["url"] == direct
    assert out["source_url"] == clean
    assert out["resolved_url"] == direct


@pytest.mark.asyncio
async def test_reverse_mock_keeps_instruction(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = await reverse_video_to_shots(
        url="https://cdn.example.com/a.mp4",
        instruction="只要 3 个镜头，强调痛点",
    )
    assert out["instruction"] == "只要 3 个镜头，强调痛点"
    assert "痛点" in out["shots"][0]["prompt"]


@pytest.mark.asyncio
async def test_reverse_empty_url() -> None:
    with pytest.raises(HTTPException) as ei:
        await reverse_video_to_shots(url="  ")
    assert ei.value.status_code == 422
