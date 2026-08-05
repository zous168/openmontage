"""单客户触达 last_sent_date 配置变更重置."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.scheduler.single_touch_idempotency import (
    reset_single_touch_daily_sent_if_plan_changed,
    single_touch_plan_signature,
)
from plugins.mxai.scheduler.state import get_last_sent_date, set_last_sent_date


def test_single_touch_plan_signature() -> None:
    assert single_touch_plan_signature({"mode": "segmented"}) is None
    assert single_touch_plan_signature(
        {"mode": "single", "time": "13:00", "recipient": "A", "message": "hi"}
    ) == ("13:00", "A", "hi")


def test_reset_clears_last_sent_when_time_changes(tmp_path) -> None:
    set_last_sent_date("wechat", "2026-07-02", data_dir=tmp_path)
    old = {"mode": "single", "time": "13:37", "recipient": "A", "message": "m"}
    new = {"mode": "single", "time": "13:46", "recipient": "A", "message": "m"}
    assert reset_single_touch_daily_sent_if_plan_changed("wechat", old, new, data_dir=tmp_path) is True
    assert get_last_sent_date("wechat", data_dir=tmp_path) is None


def test_reset_noop_when_unchanged(tmp_path) -> None:
    set_last_sent_date("wechat", "2026-07-02", data_dir=tmp_path)
    touch = {"mode": "single", "time": "13:37", "recipient": "A", "message": "m"}
    assert reset_single_touch_daily_sent_if_plan_changed("wechat", touch, dict(touch), data_dir=tmp_path) is False
    assert get_last_sent_date("wechat", data_dir=tmp_path) == "2026-07-02"


def test_workbench_put_clears_last_sent_on_time_change(
    mxai_client: TestClient,
) -> None:
    # CR-145：scheduler_state 收口 plugins/mxai/state/，经 HUB_DATA_DIR（mxai_client 已 setenv）
    # 解析；set/get 与 API 侧用同一 env 数据根，勿再另建 tmp_path。
    set_last_sent_date("wechat", "2026-07-02")
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "mode": "single",
                        "time": "14:00",
                        "recipient": "客户A",
                        "message": "回访",
                    }
                }
            }
        },
    )
    assert get_last_sent_date("wechat") is None


def test_scheduled_msg_clears_last_sent_on_recipient_change(
    mxai_client: TestClient,
) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "mode": "single",
                        "time": "14:00",
                        "recipient": "客户A",
                        "message": "回访",
                    }
                }
            }
        },
    )
    set_last_sent_date("wechat", "2026-07-02")
    mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/scheduled-msg",
        json={"recipient": "客户B", "message": "回访", "time": "14:00"},
    )
    assert get_last_sent_date("wechat") is None
