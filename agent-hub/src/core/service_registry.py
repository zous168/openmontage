"""ServiceRegistry —— 进程级 Service 注册表（LT-006.02.01）.

「插件 A 调用插件 B 的功能」的核心中介：B 经 ``provide`` 注册实现、A 经 ``get``
按**契约**解析，**双方都不互相 import**（设计 docs/Hermes插件服务共享机制设计.md §5）。

双访问入口（关键·§7.4）——本注册表是进程级单例，同时服务两条消费路径：
- **Hermes 插件**：经 ``PluginContext.provide_service / get_service``
- **hub 运行时（FastAPI/DI）**：经 ``from core.service_registry import service_registry`` 直接 ``get``，
  在 DI 组装层解析后注入无 ``ctx`` 的 hub 对象（如 SopEngine）。

契约 key 既可是 Python ``Protocol`` 类，也可是稳定字符串（带版本，如 ``"knowledge.retrieval@1"``，
供 manifest YAML 引用）——dict 键，两者皆可。解析为**懒解析**（``get`` 在调用时取，不缓存），
对 provider 热禁用安全。
"""

from __future__ import annotations

import threading
from typing import Any


class ServiceNotProvidedError(LookupError):
    """``require`` 时契约无 provider（硬依赖缺失）."""

    def __init__(self, contract: Any) -> None:
        super().__init__(f"service not provided for contract: {contract!r}")
        self.contract = contract


class ServiceRegistry:
    """契约 → 实现 的进程级注册表（线程安全）."""

    def __init__(self) -> None:
        self._services: dict[Any, Any] = {}
        self._providers: dict[Any, str] = {}  # 契约 → 提供方插件名（审计/诊断）
        self._lock = threading.Lock()

    def provide(self, contract: Any, impl: Any, *, plugin: str = "") -> None:
        """注册某契约的实现（相1 provide）。同契约后注册覆盖前者（带告警语义由调用方管）."""
        with self._lock:
            self._services[contract] = impl
            self._providers[contract] = plugin

    def get(self, contract: Any) -> Any | None:
        """解析契约实现；未 provide 返 None（软依赖据此降级）."""
        return self._services.get(contract)

    def require(self, contract: Any) -> Any:
        """解析契约实现；未 provide 抛 ServiceNotProvidedError（硬依赖）."""
        impl = self._services.get(contract)
        if impl is None:
            raise ServiceNotProvidedError(contract)
        return impl

    def is_provided(self, contract: Any) -> bool:
        return contract in self._services

    def provider_of(self, contract: Any) -> str | None:
        """该契约由哪个插件提供（诊断 / 依赖图用）."""
        return self._providers.get(contract)

    def providships(self) -> dict[Any, str]:
        """全部 契约→插件 映射快照（hermes plugins list / 依赖图用）."""
        with self._lock:
            return dict(self._providers)

    def clear(self) -> None:
        """清空（仅测试 / 进程重载用）."""
        with self._lock:
            self._services.clear()
            self._providers.clear()


# 进程级单例（双访问的共同后端）
service_registry = ServiceRegistry()
