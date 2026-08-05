"""分段定时触达 planner（CR-129）."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from core.timeutil import utc_now
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.scheduler.segmented_touch import (
    _match_segment,
    _match_touch_subtask,
    distribute_segment_run_at,
    normalize_scheduled_touch_config,
    plan_segmented_touch,
    preview_segmented_touch,
    render_touch_message,
    silence_range_zh,
    threshold_parts_to_sec,
)
from plugins.mxai.scheduler.state import (
    get_segment_last_run_date,
    get_segment_touch_at,
    set_segment_last_run_date,
    set_segment_touch,
)


def _seed_customer(
    data_dir: Path,
    uid: str,
    *,
    last_inbound_at: str,
    funnel_stage: str = "consulting",
) -> None:
    db = mxai_db_path("hub.db", data_dir)
    init_hub_schema(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO wechat_contacts (
                customer_uid, display_name, source_channel,
                funnel_stage, funnel_stage_at, created_at, updated_at, last_inbound_at
            ) VALUES (?, ?, 'wechat', ?, ?, ?, ?, ?)
            """,
            (uid, uid, funnel_stage, last_inbound_at, last_inbound_at, last_inbound_at, last_inbound_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_match_segment_boundaries() -> None:
    segs = normalize_scheduled_touch_config({"mode": "segmented", "segments": [
        {"id": "silence_1h", "enabled": True, "silence_min_sec": 3600, "silence_max_sec": 86400},
        {"id": "silence_1d", "enabled": True, "silence_min_sec": 86400, "silence_max_sec": 259200},
    ]})["segments"]
    assert _match_segment(3500, segs) is None
    hit = _match_segment(3700, segs)
    assert hit and hit["id"] == "silence_1h"
    hit2 = _match_segment(90000, segs)
    assert hit2 and hit2["id"] == "silence_1d"


def test_normalize_preserves_migrated_touch_shape() -> None:
    subtasks = [
        {
            "id": "silence_30m",
            "label": "30 分钟",
            "enabled": True,
            "threshold": {"days": 0, "hours": 0, "minutes": 30},
            "threshold_sec": 1800,
            "content_mode": "static",
            "message": "迁移后话术",
        },
        {
            "id": "revisit_1d",
            "label": "1 天",
            "enabled": False,
            "threshold": {"days": 1, "hours": 0, "minutes": 0},
            "threshold_sec": 86400,
            "content_mode": "llm",
            "ai_instruction": "询问近况",
        },
    ]
    excluded_keys = ["cid_v1_alpha", "cid_v1_beta"]

    normalized = normalize_scheduled_touch_config(
        {
            "enabled": True,
            "mode": "segmented",
            "touch_subtasks": subtasks,
            "excluded_customer_keys": excluded_keys,
        }
    )

    assert normalized["touch_subtasks"] == subtasks
    assert normalized["excluded_customer_keys"] == excluded_keys
    assert normalized["segments"] == []
    assert "excluded_customer_uids" not in normalized


def test_match_touch_subtask_picks_latest_threshold() -> None:
    subtasks = [
        {"id": "t30m", "enabled": True, "threshold_sec": 1800},
        {"id": "t90m", "enabled": True, "threshold_sec": 5400},
    ]
    hit = _match_touch_subtask(2 * 3600, subtasks)
    assert hit and hit["id"] == "t90m"
    assert _match_touch_subtask(25 * 60, subtasks) is None


def test_validate_touch_subtasks_rejects_duplicate_threshold() -> None:
    import pytest

    from plugins.mxai.scheduler.segmented_touch import validate_touch_subtasks

    touch = {
        "touch_subtasks": [
            {
                "id": "a",
                "enabled": True,
                "threshold": {"days": 0, "hours": 0, "minutes": 30},
                "content_mode": "static",
                "message": "hi",
            },
            {
                "id": "b",
                "enabled": True,
                "threshold": {"days": 0, "hours": 0, "minutes": 30},
                "content_mode": "static",
                "message": "hello",
            },
        ],
    }
    with pytest.raises(ValueError, match="duplicate touch_subtasks threshold_sec"):
        validate_touch_subtasks(touch)


def test_finalize_coerces_llm_without_instruction() -> None:
    from plugins.mxai.scheduler.segmented_touch import _finalize_touch_subtask

    row = _finalize_touch_subtask(
        {
            "id": "silence_5d",
            "enabled": True,
            "threshold_sec": 432000,
            "threshold": {"days": 5, "hours": 0, "minutes": 0},
            "content_mode": "llm",
            "ai_instruction": "",
            "message": "您好{display_name}",
        }
    )
    assert row["content_mode"] == "static"
    assert row["message"] == "您好{display_name}"

    empty = _finalize_touch_subtask(
        {
            "id": "silence_5d",
            "enabled": True,
            "threshold_sec": 432000,
            "content_mode": "llm",
            "ai_instruction": "",
        }
    )
    assert empty["content_mode"] == "llm"
    assert empty["ai_instruction"]


def test_preview_touch_subtasks_argmax_per_segment(tmp_path: Path) -> None:
    t_34m = (utc_now() - timedelta(minutes=34)).replace(microsecond=0).isoformat()
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "cust_34m", last_inbound_at=t_34m)
    _seed_customer(tmp_path, "cust_2h", last_inbound_at=t_2h)
    touch = normalize_scheduled_touch_config(
        {
            "enabled": True,
            "mode": "segmented",
            "touch_subtasks": [
                {
                    "id": "silence_30m",
                    "label": "30分钟",
                    "enabled": True,
                    "threshold": {"days": 0, "hours": 0, "minutes": 30},
                    "content_mode": "static",
                    "message": "30m",
                },
                {
                    "id": "silence_90m",
                    "label": "90分钟",
                    "enabled": True,
                    "threshold": {"days": 0, "hours": 1, "minutes": 30},
                    "content_mode": "static",
                    "message": "90m",
                },
            ],
        }
    )
    preview = preview_segmented_touch("wechat", touch, data_dir=tmp_path)
    by_id = {
        seg["id"]: {r["customer_uid"] for r in seg.get("customers") or []}
        for seg in preview["segments"]
    }
    assert "cust_34m" in by_id["silence_30m"]
    assert "cust_2h" not in by_id["silence_30m"]
    assert "cust_2h" in by_id["silence_90m"]
    assert "cust_34m" not in by_id["silence_90m"]


def test_cr155_plan_subtasks_2h_hits_90m_not_30m(tmp_path: Path) -> None:
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "cust_2h", last_inbound_at=t_2h)
    touch = normalize_scheduled_touch_config(
        {
            "enabled": True,
            "mode": "segmented",
            "touch_subtasks": [
                {
                    "id": "silence_30m",
                    "label": "30分钟",
                    "enabled": True,
                    "threshold": {"days": 0, "hours": 0, "minutes": 30},
                    "content_mode": "static",
                    "message": "30m {display_name}",
                },
                {
                    "id": "silence_90m",
                    "label": "90分钟",
                    "enabled": True,
                    "threshold": {"days": 0, "hours": 1, "minutes": 30},
                    "content_mode": "static",
                    "message": "90m {display_name}",
                },
            ],
        }
    )
    hits = plan_segmented_touch("wechat", touch, data_dir=tmp_path)
    assert len(hits) == 1
    assert hits[0].segment_id == "silence_90m"
    assert threshold_parts_to_sec({"days": 0, "hours": 1, "minutes": 30}) == 5400


def test_plan_respects_silence_and_exclusive_segment(tmp_path: Path) -> None:
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    t_2d = (utc_now() - timedelta(days=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "cust_2h", last_inbound_at=t_2h)
    _seed_customer(tmp_path, "cust_2d", last_inbound_at=t_2d)

    touch = normalize_scheduled_touch_config({
        "enabled": True,
        "mode": "segmented",
        "global_filters": {"max_enqueue_per_run": 30},
        "segments": [
            {
                "id": "silence_1h",
                "enabled": True,
                "label": "1h",
                "silence_min_sec": 3600,
                "silence_max_sec": 86400,
                "message": "hi {display_name}",
            },
            {
                "id": "silence_1d",
                "enabled": True,
                "label": "1d",
                "silence_min_sec": 86400,
                "silence_max_sec": 259200,
                "message": "hello {display_name}",
            },
        ],
    })
    hits = plan_segmented_touch("wechat", touch, data_dir=tmp_path)
    by_uid = {h.customer_uid: h.segment_id for h in hits}
    assert by_uid["cust_2h"] == "silence_1h"
    assert by_uid["cust_2d"] == "silence_1d"


def test_excluded_customer_skipped_on_enqueue(tmp_path: Path) -> None:
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "keep_me", last_inbound_at=t_2h)
    _seed_customer(tmp_path, "skip_me", last_inbound_at=t_2h)
    touch = normalize_scheduled_touch_config({
        "enabled": True,
        "mode": "segmented",
        "excluded_customer_uids": ["skip_me"],
    })
    hits = plan_segmented_touch("wechat", touch, data_dir=tmp_path)
    uids = {h.customer_uid for h in hits}
    assert "keep_me" in uids
    assert "skip_me" not in uids


def test_preview_pagination_and_selected(tmp_path: Path) -> None:
    base = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    for i in range(15):
        _seed_customer(tmp_path, f"cust_{i:02d}", last_inbound_at=base)
    touch = normalize_scheduled_touch_config({"enabled": True, "mode": "segmented"})
    body = preview_segmented_touch(
        "wechat",
        {**touch, "excluded_customer_uids": ["cust_00"]},
        segment_id="silence_1h",
        sample_limit=10,
        offset=0,
        data_dir=tmp_path,
    )
    seg = body["segments"][0]
    assert seg["match_count"] == 15
    assert seg["total_pages"] == 2
    assert len(seg["customers"]) == 10
    assert len(seg["all_customer_uids"]) == 15
    assert "cust_00" in seg["all_customer_uids"]

    page2 = preview_segmented_touch(
        "wechat",
        {**touch, "excluded_customer_uids": ["cust_00"]},
        segment_id="silence_1h",
        sample_limit=10,
        offset=10,
        data_dir=tmp_path,
    )
    all_rows = seg["customers"] + page2["segments"][0]["customers"]
    by_uid = {r["customer_uid"]: r["selected"] for r in all_rows}
    assert by_uid["cust_00"] is False
    assert all(by_uid[u] for u in by_uid if u != "cust_00")

    seg2 = page2["segments"][0]
    assert len(seg2["customers"]) == 5
    assert seg2["page"] == 2


def test_segment_touch_idempotent(tmp_path: Path) -> None:
    set_segment_touch("wechat", "silence_1h", "cust_a", "2026-07-01T00:00:00+00:00", data_dir=tmp_path)
    assert get_segment_touch_at("wechat", "silence_1h", "cust_a", data_dir=tmp_path)

    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "cust_a", last_inbound_at=t_2h)
    touch = normalize_scheduled_touch_config({"enabled": True, "mode": "segmented"})
    hits = plan_segmented_touch("wechat", touch, data_dir=tmp_path)
    assert not any(h.customer_uid == "cust_a" for h in hits)


def test_render_touch_message() -> None:
    assert render_touch_message("你好{display_name}", display_name="张三", customer_uid="wx") == "你好张三"


def test_silence_range_zh() -> None:
    assert silence_range_zh(3600, 86400) == "1小时到1天"
    assert silence_range_zh(5184000, None) == "2个月以上"


def test_distribute_segment_run_at() -> None:
    segs = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    distribute_segment_run_at(segs, "09:00", step_minutes=30)
    assert segs[0]["run_at"] == "09:00"
    assert segs[1]["run_at"] == "09:30"
    assert segs[2]["run_at"] == "10:00"


def test_normalize_interval_minutes_default() -> None:
    cfg = normalize_scheduled_touch_config({"mode": "segmented", "interval_minutes": 15})
    assert cfg["interval_minutes"] == 15
    cfg2 = normalize_scheduled_touch_config({"mode": "segmented"})
    assert cfg2["interval_minutes"] == 30


def test_segment_last_run_date(tmp_path: Path) -> None:
    set_segment_last_run_date("wechat", "silence_1h", "2026-07-01", data_dir=tmp_path)
    assert get_segment_last_run_date("wechat", "silence_1h", data_dir=tmp_path) == "2026-07-01"


def test_preview_api(mxai_client: TestClient, mxai_env: Path) -> None:
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(mxai_env, "preview_user", last_inbound_at=t_2h)
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "mode": "segmented",
                        "time": "09:00",
                    }
                }
            }
        },
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/scheduled-touch/preview",
        json={"limit": 5},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "segmented"
    assert isinstance(body.get("segments"), list)


def test_segmented_bootstrap_skips_interval_mode(
    mxai_client: TestClient,
) -> None:
    """分段触达由 interval Cron 调度，bootstrap 不入队."""
    from plugins.mxai.cfg.run_enabled import set_run_enabled
    from plugins.mxai.scheduler.benchmark_monitor import run_scheduled_touch_enqueue

    set_run_enabled("wechat", True)
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "mode": "segmented",
                        "interval_minutes": 30,
                        "segments": [
                            {
                                "id": "silence_1h",
                                "enabled": True,
                                "silence_min_sec": 3600,
                                "silence_max_sec": 86400,
                                "message": "hi",
                            }
                        ],
                    }
                }
            }
        },
    )
    result = run_scheduled_touch_enqueue(
        "wechat",
        source="bootstrap",
        operator="Bootstrap",
    )
    assert result.get("skipped") == "segmented_interval_mode"
    assert result.get("mode") == "segmented"


def test_run_dry_run_removed_use_preview(mxai_client: TestClient, mxai_env: Path) -> None:
    t_2h = (utc_now() - timedelta(hours=2)).replace(microsecond=0).isoformat()
    _seed_customer(mxai_env, "dry_user", last_inbound_at=t_2h)
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "mode": "segmented",
                        "time": "09:00",
                    }
                }
            }
        },
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/scheduled-touch/preview",
        json={"limit": 10},
    )
    assert res.status_code == 200
    assert "segments" in res.json()
    gone = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/scheduled-touch/run",
        json={},
    )
    assert gone.status_code == 200
    assert gone.json().get("ok") is True
