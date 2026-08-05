"""orchestrator 测试桩 worker（LT-032 迁移）.

v4.0 取消 hub 内置 fallback 后，队列任务须经 worker 完成。这里注册一个**桩 automan worker**：
- bridge.is_connected() → True
- execute_via_worker(task) → execute_task_handler(task)（即 automan 对该 task_type 会做的同款操作）

使依赖「任务经队列完成」的既有用例在新「单一 RPA 路径」语义下继续验证 worklog/stats/funnel 等。
需测「无 worker 离线/排队」的用例可用 `no_worker` fixture 关闭桩。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _stub_automan_worker(monkeypatch, request):
    if "no_worker" in request.keywords:
        return
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    from plugins.mxai.orchestrator.task_handlers import execute_task_handler
    from plugins.mxai.orchestrator.queue_manager import QueueManager

    # 测试隔离：清掉上一个测试可能遗留的排队任务，避免被本测试的桩 worker 误 drain。
    try:
        QueueManager.get().clear_queued()
    except Exception:
        pass

    bridge = get_rpa_worker_bridge()
    monkeypatch.setattr(bridge, "is_connected", lambda: True)

    def _fake_execute_via_worker(task, timeout: float = 600.0):
        # 桩：以 hub 内置 handler 模拟 automan 执行该 task_type，返回归一结果
        return execute_task_handler(task)

    monkeypatch.setattr(bridge, "execute_via_worker", _fake_execute_via_worker)
    yield
