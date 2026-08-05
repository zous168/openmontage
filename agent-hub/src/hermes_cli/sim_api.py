"""客户模拟（dashboard 侧）HTTP 接口 —— ``/api/customer-sim/*``。

这些是**客户模拟客户端**的接口：右下角客服浮窗（``web_dist/chat-widget.js``，由
``web_server._serve_index`` 全局注入）与坐席监控页用它们建客户主体、读会话历史、发消息。

**注意区分通用 vs 模拟**：真正"通用"的 Agent 聊天 API 在**网关 ``api_server``**
（``/api/sessions/*``，多渠道客服 Agent 实际运行处）；本模块只是 dashboard 侧的模拟器
外壳——「发消息」代理到网关 api_server，「会话读写」直读/落共享 ``state.db``（见
``hermes_cli/cs_peer_manager.py::CsPeerManager`` 与 docs §七「客服收敛到网关」）。

主体 = (channel, user_unique_id)；字段 SSOT：``channel`` + ``user_unique_id``。
经 ``web_server`` 的 ``app.include_router(router)`` 挂到 dashboard，沿用其鉴权中间件。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer-sim", tags=["customer-sim"])


class PeerCreate(BaseModel):
    channel: Optional[str] = None
    user_unique_id: Optional[str] = None
    user_display_name: Optional[str] = None


class ChatRequest(BaseModel):
    channel: Optional[str] = None
    user_unique_id: str
    message: str


def _sim_args(body: "ChatRequest") -> tuple:
    """``/api/customer-sim/{send,stream}`` 共用入参校验。"""
    channel = (body.channel or "web").strip() or "web"
    uid = (body.user_unique_id or "").strip()
    message = (body.message or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_unique_id 不能为空")
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")
    return channel, uid, message


# ── 代理到网关 api_server（客服 Agent 实际运行在网关进程；见 docs §七）──────────
def _api_server_base() -> str:
    """网关 api_server 的 loopback 基址（默认 127.0.0.1:8642，env 可覆盖）。"""
    import os

    host = (os.getenv("API_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.getenv("API_SERVER_PORT") or "8642").strip() or "8642"
    return f"http://{host}:{port}"


def _api_server_key() -> str:
    import os

    return (os.getenv("API_SERVER_KEY") or "").strip()


async def _broadcast_seat(app, payload: dict) -> None:
    """向坐席页广播一帧事件（**复用** dashboard 现成的 ``/api/events`` 广播，channel
    ``"cs-seat"`` —— 零新增传输/端点；见 `web_server._broadcast_event` / `events_ws`）。

    事件类型（让坐席页**逐 token 实时**渲染，而非每轮拉 messages）：
    - ``turn.started`` `{channel, user_unique_id, user_message}` —— 客户发问，起一轮。
    - ``delta``        `{channel, user_unique_id, delta}` —— AI 逐 token 增量。
    - ``turn.done``    `{channel, user_unique_id, user_message, reply}` —— 本轮收尾。

    坐席页据此直接渲染；仅切会话/连上/重连时才拉 ``/api/cs-seat/*`` 对齐 DB（SSOT）。
    仅进程内（dashboard 单 uvicorn 进程）；惰性 import 避免与 router 注册循环。
    """
    if app is None:
        return
    try:
        from hermes_cli.web_server import _broadcast_event

        await _broadcast_event(app, "cs-seat", json.dumps(payload, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        logger.debug("seat broadcast failed: %s", exc)


async def _cs_proxy_chat(channel: str, uid: str, message: str, app=None) -> str:
    """代理一轮对话到网关 ``api_server`` 的 ``/api/sessions/{id}/chat``，返回回复文本。

    建会话经 ``POST /api/sessions``（``profiles/{profile}/state.db``）；Agent 在网关进程内按
    ``X-Hermes-Profile`` scope 到对应业务 profile（客服默认 ``customer``）运行。
    """
    import httpx

    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    mgr = get_cs_peer_manager()
    try:
        sid, profile, session_key = mgr.resolve_target(channel, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    key = _api_server_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="网关 api_server 未配置 API_SERVER_KEY；客服功能不可用（请启用 api_server 平台并配置密钥）",
        )
    base = _api_server_base()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Hermes-Profile": profile,
        "X-Hermes-Session-Key": session_key,
    }
    url = f"{base}/api/sessions/{sid}/chat"
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, headers=headers, json={"message": message})
    except Exception as exc:  # noqa: BLE001
        logger.exception("cs proxy chat failed")
        raise HTTPException(status_code=502, detail=f"无法连接网关 api_server（{base}）：{exc}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"网关 api_server 返回 {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    reply = ((data.get("message") or {}).get("content")) or ""
    if not reply:
        raise HTTPException(status_code=502, detail="客服 Agent 未产生回复")
    # 同步路径无 delta：直接给坐席一帧 turn.done（user + 完整 reply）。
    await _broadcast_seat(app, {
        "type": "turn.done", "channel": channel, "user_unique_id": uid,
        "user_message": message, "reply": reply,
    })
    return reply


async def _cs_proxy_chat_stream(channel: str, uid: str, message: str, app=None):
    """真·逐 token 流式：透传网关 ``/api/sessions/{id}/chat/stream`` 并把其结构化事件
    （``assistant.delta`` / ``assistant.completed`` / ``error``）转换成浮窗契约
    （``data:{delta}`` / ``event:done {reply}`` / ``event:error``）。逐帧 yield SSE 字符串。
    """
    import httpx

    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    def _frame_err(status, err):
        return "event: error\ndata: " + json.dumps(
            {"status": status, "error": str(err)}, ensure_ascii=False
        ) + "\n\n"

    mgr = get_cs_peer_manager()
    try:
        sid, profile, session_key = mgr.resolve_target(channel, uid)
    except ValueError as exc:
        yield _frame_err(400, exc)
        return
    key = _api_server_key()
    if not key:
        yield _frame_err(503, "网关 api_server 未配置 API_SERVER_KEY；客服功能不可用")
        return
    base = _api_server_base()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Hermes-Profile": profile,
        "X-Hermes-Session-Key": session_key,
    }
    url = f"{base}/api/sessions/{sid}/chat/stream"
    parts: list[str] = []
    final_reply = None
    # 坐席：本轮开始（客户发问），让坐席页起一条 user 气泡 + 开始逐 token 渲染。
    await _broadcast_seat(app, {
        "type": "turn.started", "channel": channel, "user_unique_id": uid,
        "user_message": message,
    })
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", url, headers=headers, json={"message": message}
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")[:200]
                    yield _frame_err(502, f"网关 api_server 返回 {resp.status_code}: {body}")
                    return
                event = None
                data_buf: list[str] = []
                async for line in resp.aiter_lines():
                    if line == "":  # 帧边界
                        if data_buf:
                            try:
                                payload = json.loads("".join(data_buf))
                            except Exception:
                                payload = {}
                            ev = event or "message"
                            if ev in ("assistant.delta", "message"):
                                d = payload.get("delta") or ""
                                if d:
                                    parts.append(d)
                                    yield "data: " + json.dumps(
                                        {"delta": d}, ensure_ascii=False
                                    ) + "\n\n"
                                    # 先喂浮窗、再推坐席：不阻塞浮窗逐 token。
                                    await _broadcast_seat(app, {
                                        "type": "delta", "channel": channel,
                                        "user_unique_id": uid, "delta": d,
                                    })
                            elif ev == "assistant.completed":
                                final_reply = payload.get("content")
                            elif ev == "error":
                                yield _frame_err(502, payload.get("message") or "网关错误")
                                return
                        event = None
                        data_buf = []
                        continue
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buf.append(line[5:].lstrip())
    except Exception as exc:  # noqa: BLE001
        logger.exception("cs proxy stream failed")
        yield _frame_err(502, f"无法连接网关 api_server（{base}）：{exc}")
        return
    reply = final_reply if final_reply is not None else "".join(parts)
    yield "event: done\ndata: " + json.dumps(
        {"reply": reply}, ensure_ascii=False
    ) + "\n\n"
    # 坐席：本轮收尾（带 user + 完整 reply，供未收到 started 的迟到订阅者对齐）。
    await _broadcast_seat(app, {
        "type": "turn.done", "channel": channel, "user_unique_id": uid,
        "user_message": message, "reply": reply,
    })


# ── 主体（对话客户）CRUD：直读/写共享 state.db，见 cs_peer_manager.CsPeerManager ──
@router.post("/peers")
def peer_create(body: PeerCreate):
    """登记对话主体（未传 user_unique_id 时服务端生成）。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    try:
        return get_cs_peer_manager().create_peer(
            channel=body.channel or "web",
            user_unique_id=body.user_unique_id,
            user_display_name=body.user_display_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("peer create failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/peers")
def peer_list():
    """列出对话主体（含渠道、会话时间、轮次）。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    return {"peers": get_cs_peer_manager().list_peers()}


@router.get("/peers/messages")
def peer_messages(channel: str, user_unique_id: str):
    """该主体的对话历史。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    return {"messages": get_cs_peer_manager().get_history(channel, user_unique_id)}


@router.delete("/peers")
def peer_delete(channel: str, user_unique_id: str):
    """删除该主体的会话数据。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    return {"ok": get_cs_peer_manager().delete_peer(channel, user_unique_id)}


# ── 发消息：两形态严格对齐网关 api_server（同步 + SSE）──────────────────────────
@router.post("/send")
async def sim_send(body: ChatRequest, request: Request):
    """**同步**发送：代理到网关 api_server `/api/sessions/{id}/chat`，一次性返回完整回复
    `{channel, user_unique_id, reply}`。逐 token 流式见 `/api/customer-sim/stream`。"""
    channel, uid, message = _sim_args(body)
    reply = await _cs_proxy_chat(channel, uid, message, app=request.app)
    return {"channel": channel, "user_unique_id": uid, "reply": reply}


@router.post("/stream")
async def sim_stream(body: ChatRequest, request: Request):
    """**真·逐 token SSE 流式**：透传网关 api_server 的 `/chat/stream`，把结构化事件转换
    成浮窗契约（逐 token `data:{delta}`、末 `event:done {reply}`、错误 `event:error`）。"""
    channel, uid, message = _sim_args(body)
    return StreamingResponse(
        _cs_proxy_chat_stream(channel, uid, message, app=request.app),
        media_type="text/event-stream",
    )
