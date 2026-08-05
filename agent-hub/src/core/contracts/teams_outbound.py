"""teams.outbound.writer@1 契约（LT-006.04.03）—— Teams 会议纪要出站投递器.

提供方：``plugins/platforms/teams``（register 时 ``service_registry.provide`` 出
``TeamsSummaryWriter`` 类）。消费方：``plugins/teams_pipeline``（build_pipeline_runtime
从 ServiceRegistry 解析后按 platform_config 实例化），不再直 import platforms（消
plugin↔plugin 交叉）。

提供的服务对象是 **TeamsSummaryWriter 类本身**（可调用：``cls(platform_config=...)``）；
其实例暴露 ``async write_summary(payload, config, existing)``。属**可选依赖**——
platforms/teams 未加载时 ``is_provided`` 为 False，消费方优雅降级（teams_sender=None，
等价旧 ImportError 路径）。
"""

from __future__ import annotations

from typing import Any, Protocol

#: ServiceRegistry / manifest 引用 key
TEAMS_OUTBOUND_WRITER = "teams.outbound.writer@1"


class TeamsOutboundWriter(Protocol):
    """投递器实例接口（提供的服务对象是构造该实例的类）."""

    async def write_summary(self, payload: Any, config: Any, existing: Any) -> Any:
        ...
