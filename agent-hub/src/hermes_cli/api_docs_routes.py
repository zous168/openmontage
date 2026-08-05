"""8642 统一 API 文档（Dashboard + Agent api_server）."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["api-docs"])


def _api_server_host() -> str:
    return (os.getenv("API_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def _api_server_port() -> int:
    raw = (os.getenv("API_SERVER_PORT") or "18789").strip() or "18789"
    try:
        return int(raw)
    except ValueError:
        return 18789


def api_server_openapi_document() -> dict[str, Any]:
    """Agent api_server OpenAPI（Try it out 指向实际监听口，默认 18789）。"""
    from gateway.platforms.api_server import build_api_server_openapi_spec

    return build_api_server_openapi_spec(host=_api_server_host(), port=_api_server_port())


def render_unified_swagger_html() -> str:
    """8642 统一 Swagger：下拉切换 Dashboard 与 Agent API Server。

    ``urls`` 多文档模式须加载 ``swagger-ui-standalone-preset`` + ``StandaloneLayout``，
    否则 Swagger UI 只显示 "No API definition provided"。

    性能：``docExpansion: none`` 默认折叠全部 tag；加载后仅展开常用 tag；
    Models 默认隐藏（``defaultModelsExpandDepth: -1``）。
    """
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>Marketing Hub — API 文档</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js" crossorigin></script>
  <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-standalone-preset.js" crossorigin></script>
  <script>
    // 常用 tag：首屏只展开这些，其余保持折叠（减轻 400+ 操作渲染压力）
    var HUB_COMMON_TAGS = [
      "mxai",
      "mxai-agents",
      "mxai-chat",
      "mxai-queue",
      "mxai-cron",
      "auth",
      "cron",
      "sessions"
    ];

    function expandCommonTags() {
      var root = document.querySelector("#swagger-ui");
      if (!root) return;
      var wanted = {};
      HUB_COMMON_TAGS.forEach(function (t) { wanted[t.toLowerCase()] = true; });
      root.querySelectorAll(".opblock-tag-section").forEach(function (section) {
        var btn = section.querySelector("h3.opblock-tag, button.opblock-tag");
        if (!btn) return;
        var raw = (btn.getAttribute("data-tag") || btn.textContent || "").trim();
        var name = raw.split("\\n")[0].trim().toLowerCase();
        var isOpen = section.classList.contains("is-open");
        if (wanted[name] && !isOpen) {
          btn.click();
        }
      });
    }

    window.onload = function () {
      window.ui = SwaggerUIBundle({
        urls: [
          { url: "/openapi.json", name: "Dashboard 8642" },
          { url: "/openapi/api-server.json", name: "Agent API Server 18789" },
        ],
        "urls.primaryName": "Dashboard 8642",
        dom_id: "#swagger-ui",
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset,
        ],
        layout: "StandaloneLayout",
        persistAuthorization: true,
        deepLinking: true,
        validatorUrl: null,
        docExpansion: "none",
        defaultModelsExpandDepth: -1,
        defaultModelExpandDepth: -1,
        filter: true,
        tryItOutEnabled: false,
        tagsSorter: "alpha",
        operationsSorter: "alpha",
        onComplete: function () {
          setTimeout(expandCommonTags, 0);
        },
      });
    };
  </script>
</body>
</html>"""


@router.get("/docs", include_in_schema=False)
def unified_api_docs() -> HTMLResponse:
    """8642 统一 API 文档入口（本机免 IPC）。"""
    return HTMLResponse(content=render_unified_swagger_html())


@router.get("/openapi/api-server.json", include_in_schema=False)
def api_server_openapi() -> JSONResponse:
    """Agent api_server OpenAPI（供 8642 统一 Swagger 引用）。"""
    return JSONResponse(api_server_openapi_document())
