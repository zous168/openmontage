"""CR-71：MxAI MCP 工具面（队列 / 报表 / 风控）."""

from __future__ import annotations

import json

import pytest

from plugins.mxai.mcp_tools import (
    _handle_kb_search,
    _handle_materials_get,
    _handle_materials_library_detail,
    _handle_materials_list_libraries,
    _handle_materials_save,
    _handle_materials_search,
    _handle_materials_tag,
    _handle_queue_enqueue,
    _handle_queue_pause_all,
    _handle_queue_summary,
    list_tools,
)
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_mxai_mcp_catalog() -> None:
    names = {t["name"] for t in list_tools()}
    assert names == {
        "mxai_queue_enqueue",
        "mxai_queue_pause_all",
        "mxai_queue_summary",
        "mxai_report_generate",
        "mxai_risk_check",
        "mxai_risk_get_limits",
        "mxai_kb_search",  # CR-125 · FR-KB-20
        "mxai_materials_save",
        "mxai_materials_list_libraries",
        "mxai_materials_library_detail",
        "mxai_materials_search",
        "mxai_materials_get",
        "mxai_materials_tag",
    }


def test_mxai_kb_search_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-125 · FR-KB-20：kb_search 工具复用混合检索，返回命中切片；支持 partition 过滤。"""
    import plugins.mxai.kb.client as kbc

    monkeypatch.setattr(
        kbc,
        "search",
        lambda q, *, limit=5, data_dir=None: [
            {"text": "本地部署支持纯离线。", "doc_id": "d1", "seq": 3,
             "partition_id": "产品手册", "score": 0.9, "matched_via": "hybrid"},
            {"text": "售后片", "doc_id": "d2", "seq": 1,
             "partition_id": "售后", "score": 0.5, "matched_via": "text"},
        ],
    )
    # query 必填
    assert json.loads(_handle_kb_search({"query": ""}))["error"]
    # 命中两片
    out = json.loads(_handle_kb_search({"query": "支持本地部署吗", "top_k": 5}))
    assert out["count"] == 2
    assert out["hits"][0]["doc_id"] == "d1"
    assert out["hits"][0]["partition"] == "产品手册"
    assert out["hits"][0]["matched_via"] == "hybrid"
    # partition 过滤 → 仅产品手册
    out2 = json.loads(_handle_kb_search({"query": "x", "partitions": ["产品手册"]}))
    assert out2["count"] == 1
    assert out2["hits"][0]["partition"] == "产品手册"


def test_mxai_materials_save_tool(mxai_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_name = "img_materialstest01.jpg"
    img_path = cache_dir / img_name
    img_path.write_bytes(b"\xff\xd8\xff" + b"x" * 64)

    out = json.loads(
        _handle_materials_save(
            {
                "file_path": f"[mxai-image:{img_name}]",
                "display_name": "微信产品图.jpg",
                "tags": ["微信"],
            }
        )
    )
    assert out["asset_id"]
    assert out["display_name"] == "微信产品图.jpg"
    assert "微信" in out.get("tags", [])
    assert "素材库" in out.get("text", "")

    dup = json.loads(_handle_materials_save({"file_path": str(img_path)}))
    assert dup.get("duplicate_skipped") is True


def test_mxai_materials_browse_and_get(mxai_env) -> None:
    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_path = cache_dir / "img_browse01.jpg"
    img_path.write_bytes(b"\xff\xd8\xff" + b"y" * 32)

    saved = json.loads(
        _handle_materials_save(
            {"file_path": str(img_path), "display_name": "browse-test.jpg"}
        )
    )
    asset_id = saved["asset_id"]
    lib_id = saved["library_id"]

    libs = json.loads(_handle_materials_list_libraries({}))
    assert libs["count"] >= 1
    assert any(int(x["library_id"]) == int(lib_id) for x in libs["libraries"])

    detail = json.loads(_handle_materials_library_detail({"library_id": lib_id}))
    assert detail["asset_total"] >= 1
    assert "folders" in detail

    search = json.loads(
        _handle_materials_search({"library_id": lib_id, "query": "browse"})
    )
    assert search["total"] >= 1

    got = json.loads(_handle_materials_get({"asset_id": asset_id}))
    assert got["file_exists"] is True
    assert got["preview_url"].endswith(f"/assets/{asset_id}/preview")


def test_mxai_materials_tag_tool(mxai_env) -> None:
    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    img_path = cache_dir / "img_tagtool01.jpg"
    img_path.write_bytes(b"\xff\xd8\xff" + b"b" * 32)
    saved = json.loads(
        _handle_materials_save({"file_path": str(img_path), "tags": ["初始"]})
    )
    asset_id = saved["asset_id"]

    added = json.loads(
        _handle_materials_tag(
            {"asset_id": asset_id, "tags": ["产品图", "微信"], "mode": "add"}
        )
    )
    assert "产品图" in added.get("tags", [])
    assert "微信" in added.get("tags", [])
    assert "初始" in added.get("tags", [])

    removed = json.loads(
        _handle_materials_tag({"asset_id": asset_id, "tags": ["初始"], "mode": "remove"})
    )
    assert "初始" not in removed.get("tags", [])


def test_mxai_queue_enqueue(mxai_env) -> None:
    QueueManager.reset()
    QueueManager.get().arm_work()  # CR-85：未开始工作不可入队，先武装
    raw = _handle_queue_enqueue(
        {
            "profile_id": "douyin",
            "task_type": "comment_collect",
            "name": "评论意向客户采集",
            "payload": {"keywords": ["咨询"]},
        }
    )
    data = json.loads(raw)
    assert data["task_id"]
    assert data["task_type"] == "comment_collect"
    q = QueueManager.get()
    assert any(t.task_type == "comment_collect" for t in q._tasks.values())


def test_mxai_queue_enqueue_rejects_unentitled_profile(
    mxai_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.is_profile_entitled",
        lambda pid: pid != "boss",
    )
    QueueManager.reset()
    QueueManager.get().arm_work()
    raw = _handle_queue_enqueue(
        {
            "profile_id": "boss",
            "task_type": "greet",
            "name": "打招呼",
        }
    )
    data = json.loads(raw)
    assert data.get("error")
    assert "未授权" in data["error"]


def test_mxai_queue_pause_and_summary(mxai_env) -> None:
    QueueManager.reset()
    pause_raw = _handle_queue_pause_all({"paused": True, "disable_agents": True})
    pause = json.loads(pause_raw)
    assert pause["paused"] is True

    summary_raw = _handle_queue_summary({})
    summary = json.loads(summary_raw)
    assert "queued" in summary


def test_floating_chat_blocks_materials_save_for_view(
    mxai_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.mxai.agents.assistant import (
        ASSISTANT_CHANNEL_FLOATING,
        assistant_channel_session_id,
    )

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    tokens = set_session_vars(session_id=sid)
    monkeypatch.setenv("HERMES_SESSION_USER_MESSAGE", "看一下 desktop.jpg")
    try:
        out = json.loads(
            _handle_materials_save(
                {"file_path": r"C:\Users\zhaoh\Desktop\desktop.jpg"}
            )
        )
        assert "error" in out
        assert "MEDIA:" in out["error"]
    finally:
        clear_session_vars(tokens)
        monkeypatch.delenv("HERMES_SESSION_USER_MESSAGE", raising=False)


def test_floating_chat_allows_materials_save_with_save_intent(
    mxai_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.platforms.base import get_image_cache_dir
    from gateway.session_context import clear_session_vars, set_session_vars
    from plugins.mxai.agents.assistant import (
        ASSISTANT_CHANNEL_FLOATING,
        assistant_channel_session_id,
    )

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_path = cache_dir / "img_float_save01.jpg"
    img_path.write_bytes(b"\xff\xd8\xff" + b"x" * 32)

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    tokens = set_session_vars(session_id=sid)
    monkeypatch.setenv("HERMES_SESSION_USER_MESSAGE", "保存到素材库")
    try:
        out = json.loads(_handle_materials_save({"file_path": str(img_path)}))
        assert out.get("asset_id")
    finally:
        clear_session_vars(tokens)
        monkeypatch.delenv("HERMES_SESSION_USER_MESSAGE", raising=False)


def test_assistant_hermes_path(monkeypatch: pytest.MonkeyPatch, mxai_client) -> None:
    from plugins.mxai.agents import assistant as mod

    monkeypatch.setenv("API_SERVER_KEY", "test-key")
    monkeypatch.setenv("MXAI_MOCK", "0")

    def fake_hermes(message: str, **_kw):
        assert message == "帮我查队列"
        return {"text": "Hermes 队列 OK", "source": "assistant_tool"}

    monkeypatch.setattr(mod, "_hermes_session_chat", fake_hermes)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "帮我查队列", "agent": "assistant", "stream": False},
    ).json()
    assert body["reply"]["text"] == "Hermes 队列 OK"
    assert body["reply"]["source"] == "assistant_tool"
    assert body["hermes_profile"] == "assistant"
    assert body["session_id"] == "mxai-assistant-floating-chat"
