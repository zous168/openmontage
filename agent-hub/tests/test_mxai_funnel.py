"""获客转化漏斗 CRM 聚合（CR-63 / FR-REPORT-06）."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.funnel import report_funnel, funnel_drill
from plugins.mxai.crm.storage.hub_repo import init_hub_schema


def _seed_funnel_db(db_path: Path) -> None:
    init_hub_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO douyin_leads (
                lead_id, source_channel, source_comment,
                author, intent_level, funnel_stage, funnel_stage_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "lead_a",
                "douyin",
                "多少钱",
                "用户A",
                "高",
                "intent_qualified",
            ),
        )
        conn.execute(
            """
            INSERT INTO douyin_leads (
                lead_id, source_channel, source_comment,
                author, intent_level, funnel_stage, funnel_stage_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '-1 day'))
            """,
            (
                "lead_b",
                "douyin",
                "咨询",
                "用户B",
                "高",
                "dm_reached",
            ),
        )
        conn.execute(
            """
            INSERT INTO wechat_contacts (
                customer_uid, display_name, source_channel,
                funnel_stage, funnel_stage_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))
            """,
            ("cust_c", "张总", "wechat", "consulting"),
        )
        conn.commit()
    finally:
        conn.close()


def test_report_funnel_crm_cohort(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    _seed_funnel_db(db)
    data_dir = tmp_path
    # hub.db at data_dir/hub.db
    result = report_funnel(7, data_dir=data_dir)
    assert result["source"] == "crm"
    stages = result["stages"]
    assert len(stages) == 5
    assert stages[0]["stage_key"] == "comment_lead"
    assert stages[0]["value"] == 2
    assert stages[1]["value"] == 2
    assert stages[2]["value"] == 1
    for i in range(len(stages) - 1):
        assert stages[i]["value"] >= stages[i + 1]["value"]


def test_funnel_drill_matches_layer(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    _seed_funnel_db(db)
    layer = report_funnel(7, data_dir=tmp_path)["stages"][2]
    drill = funnel_drill("dm_reached", range_days=7, data_dir=tmp_path)
    assert drill["total"] == layer["value"]
    assert drill["items"][0]["entity"] == "lead"


def test_funnel_api(mxai_client: TestClient) -> None:
    funnel = mxai_client.get("/api/plugins/mxai/reports/funnel?range_days=7").json()
    assert funnel["source"] == "crm"
    assert len(funnel["stages"]) == 5
    stage_keys = [s["stage_key"] for s in funnel["stages"]]
    assert stage_keys == [
        "comment_lead",
        "intent_qualified",
        "dm_reached",
        "friend_added",
        "consulting",
    ]
    drill = mxai_client.get(
        "/api/plugins/mxai/reports/funnel/drill",
        params={"stage_key": "comment_lead", "range_days": 7},
    )
    assert drill.status_code == 200
    body = drill.json()
    assert body["stage_key"] == "comment_lead"
    assert body["total"] == funnel["stages"][0]["value"]
