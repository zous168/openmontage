"""Boss greet：workbench 补全 zhiwei，避免 automan 键盘空粘贴."""

from __future__ import annotations

from unittest.mock import patch

from plugins.mxai.rpa_worker import automan_bridge as ab
from plugins.mxai.scheduler.boss_greet_schedule import (
    _build_payload,
    enrich_greet_plan_from_workbench,
)


def test_enrich_greet_plan_fills_zhiwei_from_workbench():
    cfg = {
        "greet_plans": [
            {
                "id": "gp_default",
                "enqueue_at": "14:45",
                "new_number": 4,
                "zhiwei": "私域合伙人",
                "zhize": "操盘经验",
            }
        ],
        "workbench": {"boss": {"greet_position": ""}},
    }
    plan = enrich_greet_plan_from_workbench(
        "boss",
        {"id": "gp_default", "enqueue_at": "14:45", "new_number": 4},
        cfg=cfg,
    )
    assert plan["zhiwei"] == "私域合伙人"
    assert plan["zhize"] == "操盘经验"
    payload = _build_payload(plan, [])
    assert payload["zhiwei"] == "私域合伙人"
    assert payload["zhize"] == "操盘经验"
    assert payload["new_number"] == 4


def test_inputs_for_greet_enriches_missing_zhiwei():
    cfg = {
        "greet_plans": [
            {"id": "gp_x", "zhiwei": "Java工程师", "zhize": "3年", "new_number": 8}
        ],
        "workbench": {"boss": {}},
    }
    with patch(
        "plugins.mxai.scheduler.boss_greet_schedule._read_boss_greet_cfg",
        return_value=cfg,
    ):
        inputs = ab._inputs_for(
            "greet",
            {"plan_id": "gp_x", "candidates": [], "template": ""},
        )
    assert inputs["zhiwei"] == "Java工程师"
    assert inputs["zhize"] == "3年"
    assert inputs["new_number"] == 8
