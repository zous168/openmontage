"""core —— Hermes 中立核心层（契约 + 服务注册表）.

存放 **既不属于任一插件、也不属于 hub 运行时** 的跨界契约与机制（LT-006）：
- ``service_registry``  进程级 Service 注册表（Hermes 插件 ctx 与 hub DI 的共同后端）
- ``contracts/``        插件间共享能力的 Protocol 契约（A/B 都只 import 这里，互不 import）
- ``platform/``           本机 IPC、设备鉴权、租户 ContextVar

依赖方向：plugins / hub / middlewares → ``core``（单向）；``core`` 不依赖 plugins / hub。
"""
