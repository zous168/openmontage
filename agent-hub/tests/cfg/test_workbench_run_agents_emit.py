"""workbench 变更后推送 run.agents（Dashboard modules[] 热同步）."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_workbench_patch_emits_run_agents(mxai_client: TestClient) -> None:
    with patch("plugins.mxai.cfg.domains.emit_run_agents") as emit:
        res = mxai_client.put(
            "/api/plugins/mxai/agents/douyin/workbench",
            json={"data": {"comment_collect": {"enabled": False}}},
        )
        assert res.status_code == 200
        emit.assert_called()
