"""Marketing Hub - FastAPI 组合根（Hermes 为根 · LT-007.02.02）.



Hermes 为根 ASGI；本机 IPC / 设备鉴权在 ``core.platform`` + ``dashboard_auth``.



启动::



    $env:PYTHONPATH = ".\\src"   # 从 agent-hub 目录运行

    python -m uvicorn main:app --host 127.0.0.1 --port 8642

    # 数据目录：源码 dev 默认 {repo}/.data；打包 sidecar 默认 {安装目录}/data
"""



import os

import sys

from pathlib import Path  # noqa: E402



sys.path.insert(0, str(Path(__file__).parent))



from src.runtime_paths import bootstrap_marketing_hub_runtime  # noqa: E402



_RUNTIME_PATHS = bootstrap_marketing_hub_runtime()



import structlog  # noqa: E402

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402



from core.platform.device.local_ipc import validate_ipc_token  # noqa: E402

from hermes_cli.web_server import app, finalize_routes  # noqa: E402

from src.middlewares.trace_middleware import TraceMiddleware  # noqa: E402



logger = structlog.get_logger("marketing_hub.main")

logger.info("runtime.paths", **_RUNTIME_PATHS)



# 请求顺序：CORS → Trace → (Hermes dashboard_auth: local_guard + gated) → route

app.add_middleware(TraceMiddleware)

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=False,

    allow_methods=["*"],

    allow_headers=["*"],

)





@app.get("/health")

async def health() -> dict:

    return {"status": "ok", "service": "marketing-hub"}





try:

    from hermes_cli.integrated_mount import configure_integrated_dashboard

    from hermes_cli.plugins import discover_plugins



    _api_host = os.environ.get("HUB_API_HOST", "127.0.0.1").strip() or "127.0.0.1"

    _api_port = int(os.environ.get("HUB_API_PORT", "8642"))

    _gated = configure_integrated_dashboard(

        app,

        host=_api_host,

        port=_api_port,

        ipc_token_validator=validate_ipc_token,

    )

    discover_plugins()

    from hermes_cli.web_routes.oauth_messaging import set_channels_platform_allowlist

    set_channels_platform_allowlist(
        frozenset({"wecom", "clawbot", "feishu", "dingtalk"}),
        display_order=("clawbot", "wecom", "feishu", "dingtalk"),
    )

    from hermes_cli.memory_routing import wire_memory_routing

    wire_memory_routing()

    finalize_routes(app)

    from hermes_cli.gateway_lifecycle import wire_gateway_lifecycle

    wire_gateway_lifecycle(app)

    logger.info(

        "hermes.root.configured",

        dashboard_gated=_gated,

        data_dir=_RUNTIME_PATHS["data_dir"],

    )

except Exception as _cfg_exc:  # noqa: BLE001

    logger.warning("hermes.root.configure_failed", err=str(_cfg_exc))

