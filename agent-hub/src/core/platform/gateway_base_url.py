"""平台 LLM 网关基址：优先 ``LLM_GATEWAY_BASE_URL``，缺省回退 ``CONTROL_SERVER_BASE_URL``。

边缘 nginx「平台一体」同口分流（``/api``→CS、``/v1``→LLM）时二者同 host:port；
本地 dev 网关与 CS 分端口时仍可通过显式 ``LLM_GATEWAY_BASE_URL`` 覆盖。
"""

from __future__ import annotations

import os

LLM_GATEWAY_BASE_URL_ENV = "LLM_GATEWAY_BASE_URL"
CONTROL_SERVER_BASE_URL_ENV = "CONTROL_SERVER_BASE_URL"


def resolve_llm_gateway_base_url() -> str:
    gw = (os.getenv(LLM_GATEWAY_BASE_URL_ENV, "") or "").strip().rstrip("/")
    if gw:
        return gw
    return (os.getenv(CONTROL_SERVER_BASE_URL_ENV, "") or "").strip().rstrip("/")
