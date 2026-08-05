"""复现「王德撒大苏打@微信」分段触达未命中预览的真实根因：segment_touched 幂等.

只读诊断脚本 `scripts/diagnose_touch_filters_only.py` 在现网数据上跑出的结论：
  - last_inbound_at 有效，静默 6.4h → 命中 silence_1h
  - scheduler_state.touches.silence_1h 已有该 UID → _passes_filters 返回 segment_touched
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.scheduler.segmented_touch import (
    collect_segmented_touch_candidates,
    normalize_scheduled_touch_config,
)
from plugins.mxai.scheduler.state import set_segment_touch
from core.timeutil import utc_now, utc_now_iso


def _seed_customer(data_dir: Path, uid: str, *, last_inbound_at: str) -> None:
    import sqlite3

    db = mxai_db_path("hub.db", data_dir)
    init_hub_schema(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO wecom_contacts (
                customer_uid, display_name, source_channel,
                funnel_stage, funnel_stage_at, created_at, updated_at, last_inbound_at
            ) VALUES (?, ?, 'qiyeweixin', 'consulting', ?, ?, ?, ?)
            """,
            (uid, uid, last_inbound_at, last_inbound_at, last_inbound_at, last_inbound_at),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("uid", ["王德撒大苏打@微信"])
def test_segment_touched_excludes_from_preview(tmp_path: Path, uid: str) -> None:
    """与现网 scheduler_state 一致：该客户已在 silence_1h 触达过 → 预览不再出现."""
    now = utc_now()
    # 模拟现网：入站约 6.4h 前（落在 silence_1h 窗口内）
    inbound_at = (now - timedelta(hours=6, minutes=25)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    _seed_customer(tmp_path, uid, last_inbound_at=inbound_at)

    touch_cfg = normalize_scheduled_touch_config(
        {
            "enabled": True,
            "mode": "segmented",
            "global_filters": {"max_enqueue_per_run": 30},
        }
    )

    # 未触达前：应命中 silence_1h
    before = collect_segmented_touch_candidates(
        "qiyeweixin", touch_cfg, include_excluded=False, data_dir=tmp_path
    )
    assert any(h.customer_uid == uid and h.segment_id == "silence_1h" for h in before)

    # 模拟现网 scheduler_state：08:11 UTC 已对该客户 silence_1h 触达
    set_segment_touch(
        "qiyeweixin",
        "silence_1h",
        uid,
        utc_now_iso(),
        data_dir=tmp_path,
    )

    after = collect_segmented_touch_candidates(
        "qiyeweixin", touch_cfg, include_excluded=False, data_dir=tmp_path
    )
    assert not any(h.customer_uid == uid for h in after), (
        "segment_touched 幂等：同分段已触达后不应再进预览"
    )


def test_without_prior_touch_still_matches_silence_1h(tmp_path: Path) -> None:
    """对照：无 touch_record 时，6h 静默客户应进 silence_1h."""
    uid = "王德撒大苏打@微信"
    now = utc_now()
    inbound_at = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    _seed_customer(tmp_path, uid, last_inbound_at=inbound_at)

    touch_cfg = normalize_scheduled_touch_config({"enabled": True, "mode": "segmented"})
    hits = collect_segmented_touch_candidates(
        "qiyeweixin", touch_cfg, include_excluded=False, data_dir=tmp_path
    )
    assert len(hits) == 1
    assert hits[0].segment_id == "silence_1h"
