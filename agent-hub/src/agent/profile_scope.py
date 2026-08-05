"""进程内为某 profile 运行 agent 的正确作用域原语。

单进程内要让一个"为某 profile 运行的 AIAgent（含其后台线程）"读写**正确的**
``HERMES_HOME``，靠 :data:`hermes_constants._HERMES_HOME_OVERRIDE`（一个
``ContextVar``）。本模块提供整轮持有该覆盖的上下文管理器。

ContextVar 不会自动传到 ``threading.Thread`` / ``ThreadPoolExecutor`` 工作线程，
故 agent 运行时 spawn 后台线程（bg-review / curator / 记忆同步 / 标题）的各处已用
``tools.thread_context.propagate_context_to_thread`` 在 spawn 时 ``copy_context()``
把覆盖快照带入子线程。**前提**：spawn 发生时父线程必须正持有覆盖——即下面的
"正确用法不变式"。

正确用法不变式
--------------
1. **set override 必须与 ``run_conversation`` 同线程**。``run_conversation`` 是
   同步阻塞调用、主循环跑在调用者线程，后台线程都在其内 spawn。若调用方是
   asyncio（如 dashboard），必须把"构造 agent + run_conversation"整体作为
   提交给 executor 的**同一个同步 callable**（``run_in_executor``），在该
   线程内进入本 scope；**切勿**只在事件循环协程里 set 覆盖。
2. **整轮持有**：构造 agent 与每一次 ``run_conversation`` 都在 scope 内执行；
   ``run_conversation`` 返回后再退出 scope（reset）。后台线程在 spawn 时已
   ``copy_context()`` 值拷贝快照，主线程随后 reset **不影响**子线程快照。
3. **显式注入 SessionDB**：``hermes_state.SessionDB`` 的默认路径是 import 期常量，
   不跟随覆盖。构造 agent 时显式传 ``SessionDB(db_path=profile_home/"state.db")``
   （见 :func:`profile_session_db`），勿依赖 ``DEFAULT_DB_PATH``。
4. **进程内 profile 只由本覆盖决定，绝不由进程级环境变量决定**。``HERMES_PROFILE``
   / ``HERMES_HOME`` 是全进程共享、无法按 profile 区分——集成 dashboard 启动时由
   ``hermes_cli.integrated_mount.purge_profile_env()`` 抹除二者；这些 env 仅用于向
   **子进程**注入。切勿在进程内 ``os.environ[...]=`` 设置它们。

用法::

    from agent.profile_scope import hermes_profile_scope, profile_session_db

    with hermes_profile_scope(profile_home):
        agent = build_agent(..., session_db=profile_session_db(profile_home))
        result = agent.run_conversation(user_message)
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hermes_constants import reset_hermes_home_override, set_hermes_home_override

PathLike = str | Path


@contextmanager
def hermes_profile_scope(profile_home: PathLike) -> Iterator[Path]:
    """整轮持有 ``HERMES_HOME`` 覆盖（构造 + run_conversation 全程）。

    见模块文档的"正确用法不变式"。``yield`` 出 ``profile_home`` 的 ``Path``。
    """
    home = Path(profile_home)
    token = set_hermes_home_override(str(home))
    try:
        yield home
    finally:
        reset_hermes_home_override(token)


def profile_session_db(profile_home: PathLike):
    """返回锚定到该 profile ``state.db`` 的 ``SessionDB``（显式注入用）。

    绕开 ``hermes_state.DEFAULT_DB_PATH``（import 期常量、不跟随覆盖）。
    """
    from hermes_state import SessionDB

    return SessionDB(db_path=Path(profile_home) / "state.db")
