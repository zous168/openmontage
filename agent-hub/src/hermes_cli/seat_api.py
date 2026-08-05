"""坐席接待监控（dashboard 侧）HTTP 接口 —— ``/api/cs-seat/*``（只读）。

坐席页（前端 `/seat`）的后端：**只读**列出进行中的客服会话 + 读对话历史，供人工旁观。

**命名归属**：``cs-seat`` = 客服坐席（agent 侧监控），刻意区别于 ``customer-sim``
（客户模拟客户端，见 ``hermes_cli/sim_api.py`` 的 ``/api/customer-sim/*``）与网关通用
``/api/sessions/*``。两者共享同一 dashboard 进程的会话存储——``CsPeerManager``
直读共享 ``state.db``（见 ``hermes_cli/cs_peer_manager.py`` 与 docs §七）。

本期纯 AI 只读监控；人工接管（转人工）延后 P2。经 ``web_server.include_router`` 挂载。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cs-seat", tags=["cs-seat"])


@router.get("/peers")
def seat_peers():
    """列出进行中的客服会话（含渠道、会话时间、轮次）——坐席监控用。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    return {"peers": get_cs_peer_manager().list_peers()}


@router.get("/peers/messages")
def seat_peer_messages(channel: str, user_unique_id: str):
    """该会话的对话历史——坐席监控用。"""
    from hermes_cli.cs_peer_manager import get_cs_peer_manager

    return {"messages": get_cs_peer_manager().get_history(channel, user_unique_id)}
