"""CR-155 fixture seed / cleanup / preview baseline tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.timeutil import BEIJING
from plugins.mxai.cfg.bootstrap.cr155_fixture_seed import (
    CUST_PREFIX,
    cleanup_cr155_touch_fixtures,
    seed_cr155_touch_fixtures,
)
from plugins.mxai.cfg.paths import agent_cfg_path, mxai_db_path
from plugins.mxai.cfg.store import read_yaml
from plugins.mxai.cfg.workbench_scheduler import extract_scheduler
from plugins.mxai.scheduler.segmented_touch import preview_segmented_touch


def _fixed_t0() -> datetime:
    return datetime(2026, 7, 15, 3, 0, 0, tzinfo=UTC)


def _segment_customer_map(preview: dict, segment_id: str) -> dict[str, dict]:
    for seg in preview.get("segments") or []:
        if str(seg.get("id")) == segment_id:
            rows = seg.get("customers") or seg.get("samples") or []
            return {str(r["customer_uid"]): r for r in rows}
    return {}


def test_seed_and_cleanup_idempotent(tmp_path: Path) -> None:
    first = seed_cr155_touch_fixtures(tmp_path, t0=_fixed_t0())
    second = seed_cr155_touch_fixtures(tmp_path, t0=_fixed_t0())
    assert first.customers_wechat == 17
    assert first.customers_qiyeweixin == 5
    assert first.deliveries == 8
    assert second.customers_wechat == first.customers_wechat
    assert second.deliveries == first.deliveries

    cleanup = cleanup_cr155_touch_fixtures(tmp_path)
    assert cleanup["remaining_customers"] == 0

    db = mxai_db_path("hub.db", tmp_path)
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        n = int(
            conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM wechat_touch_deliveries WHERE delivery_id LIKE 'cr155_fixture_delivery_%')
                + (SELECT COUNT(*) FROM wecom_touch_deliveries WHERE delivery_id LIKE 'cr155_fixture_delivery_%')
                """
            ).fetchone()[0]
        )
        assert n == 0
    finally:
        conn.close()


def test_wechat_preview_baseline(tmp_path: Path, monkeypatch) -> None:
    t0 = _fixed_t0()
    seed_cr155_touch_fixtures(tmp_path, t0=t0)
    monkeypatch.setattr("plugins.mxai.scheduler.segmented_touch.utc_now", lambda: t0)
    biz_date = t0.astimezone(BEIJING).date().isoformat()
    monkeypatch.setattr(
        "plugins.mxai.scheduler.touch_delivery_service.beijing_business_date",
        lambda: biz_date,
    )
    wb = read_yaml(agent_cfg_path("wechat", "workbench.yaml", tmp_path), {})
    sched = extract_scheduler(wb, has_benchmarks=False)
    touch = sched["scheduled_touch"]
    preview = preview_segmented_touch("wechat", touch, data_dir=tmp_path)

    m30 = _segment_customer_map(preview, "cr155_touch_30m")
    m40 = _segment_customer_map(preview, "cr155_touch_40m")
    m90 = _segment_customer_map(preview, "cr155_touch_90m")
    m3d = _segment_customer_map(preview, "cr155_touch_3d")

    assert f"{CUST_PREFIX}w01" in m30
    assert f"{CUST_PREFIX}w06" in m30
    assert f"{CUST_PREFIX}w12" in m30
    assert f"{CUST_PREFIX}w15" in m30
    assert m30[f"{CUST_PREFIX}w01"]["selected"] is True
    assert f"{CUST_PREFIX}w14" not in m30
    assert f"{CUST_PREFIX}w13" not in m30

    assert f"{CUST_PREFIX}w02" in m40
    assert f"{CUST_PREFIX}w08" in m40
    assert m40[f"{CUST_PREFIX}w08"]["selected"] is False
    assert f"{CUST_PREFIX}w07a" not in m40
    assert f"{CUST_PREFIX}w10" not in m40
    assert f"{CUST_PREFIX}w11" not in m40

    assert f"{CUST_PREFIX}w03" in m90
    assert f"{CUST_PREFIX}w09" not in m90

    assert f"{CUST_PREFIX}w04" in m3d


def test_qiyeweixin_preview_baseline(tmp_path: Path, monkeypatch) -> None:
    t0 = _fixed_t0()
    seed_cr155_touch_fixtures(tmp_path, t0=t0)
    monkeypatch.setattr("plugins.mxai.scheduler.segmented_touch.utc_now", lambda: t0)
    wb = read_yaml(agent_cfg_path("qiyeweixin", "workbench.yaml", tmp_path), {})
    sched = extract_scheduler(wb, has_benchmarks=False)
    touch = sched["scheduled_touch"]
    preview = preview_segmented_touch("qiyeweixin", touch, data_dir=tmp_path)

    m30 = _segment_customer_map(preview, "cr155_touch_30m")
    m40 = _segment_customer_map(preview, "cr155_touch_40m")
    m90 = _segment_customer_map(preview, "cr155_touch_90m")

    assert f"{CUST_PREFIX}q01" in m30
    assert f"{CUST_PREFIX}q02" in m40
    assert f"{CUST_PREFIX}q03a" not in m40
    assert f"{CUST_PREFIX}q04" in m90
