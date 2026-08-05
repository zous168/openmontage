"""FR-WB-05 实时 Agent 数：按已开工渠道启用状态统计，非 RPA 瞬时执行数."""

from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.stats.service import stats_realtime


def test_stats_realtime_idle_when_not_armed(mxai_env) -> None:
    del mxai_env
    QueueManager.reset()
    rt = stats_realtime()
    assert rt["work_armed"] is False
    assert rt["running_agents"] == 0
    assert rt["idle_agents"] == 0


def test_stats_realtime_counts_enabled_channels_when_armed(mxai_env) -> None:
    del mxai_env
    QueueManager.reset()
    q = QueueManager.get()
    q.arm_work()
    q.set_agent_enabled("douyin", True)
    q.set_agent_enabled("xiaohongshu", True)
    q.set_agent_enabled("wechat", True)
    q.set_agent_enabled("boss", True)
    rt = stats_realtime()
    assert rt["work_armed"] is True
    assert rt["running_agents"] == 4
    assert rt["idle_agents"] == 2
