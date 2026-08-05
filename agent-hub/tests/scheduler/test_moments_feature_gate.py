"""CR-168 · moments 三门 G3_config."""

from __future__ import annotations

from plugins.mxai.scheduler.cron import _feature_config_allows


def test_moments_feature_requires_enabled_and_scheduled() -> None:
    wb_off = {"moments": {"enabled": False, "days": {"2026-08-01": [{"id": "a", "time": "08:00", "status": "scheduled"}]}}}
    assert _feature_config_allows("wechat", "moments", wb_off) is False

    wb_empty = {"moments": {"enabled": True, "days": {}}}
    assert _feature_config_allows("wechat", "moments", wb_empty) is False

    wb_ok = {
        "moments": {
            "enabled": True,
            "days": {
                "2026-08-01": [
                    {"id": "a", "time": "08:00", "status": "scheduled", "mode": "text", "content": "x"},
                ]
            },
        }
    }
    assert _feature_config_allows("wechat", "moments", wb_ok) is True
    assert _feature_config_allows("qiyeweixin", "moments", wb_ok) is False
