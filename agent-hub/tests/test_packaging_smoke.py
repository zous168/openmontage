"""客户端 CI 打包门禁：hub 侧车须可导入、路由可注册（不测全量后端单测）."""

from __future__ import annotations


def test_mxai_router_importable() -> None:
    from plugins.mxai.api.router import router

    assert len(router.routes) > 0

