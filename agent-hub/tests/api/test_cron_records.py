"""任务调度记录视图（CR-135 · LT-039.01）后端聚合端点测试.

单元：``_aggregate_cron_records`` / ``_parse_job_id`` / ``_derive_record_status`` 纯逻辑
（monkeypatch 注入的 cron.jobs helper，不依赖真实 profile 目录）。
集成：``GET /api/plugins/mxai/cron/records`` 形状 + 只读鉴权行为（与其它 mxai 只读端点一致）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from plugins.mxai.api.cron import (
    RUNNING_GRACE_SECONDS,
    _aggregate_cron_records,
    _derive_record_status,
    _parse_job_id,
)

TZ = timezone(timedelta(hours=8))  # 北京固定偏移（避免依赖 tzdata）
NOW = datetime(2026, 7, 5, 17, 0, 0, tzinfo=TZ)


# ---------------------------------------------------------------------------
# 记录全文构造
# ---------------------------------------------------------------------------
def content_ok(msg: str = "【定时触达】wechat 入队 3 条") -> str:
    return (
        "# Cron Job: t\n\n**Job ID:** j\n\n## 同步返回\n\n"
        '{"ok": true}\n\n---\n\n## Callback 返回（异步）\n\n'
        "**Callback Time:** 2026-07-05 09:30:15\n"
        "**Success:** True\n**Deliver:** local\n\n" + msg + "\n"
    )


def content_running() -> str:
    """有同步返回节、尚无 Callback 节。"""
    return "# Cron Job: t\n\n**Job ID:** j\n\n## 同步返回\n\n{\"ok\": true}\n"


def content_fail_callback() -> str:
    return (
        "# Cron Job: t\n\n## 同步返回\n\n{}\n\n---\n\n## Callback 返回（异步）\n\n"
        "**Success:** False\n**Deliver:** local\n\n执行失败\n"
    )


def content_fail_http() -> str:
    return "# Cron Job: t (FAILED)\n\n## Error\n\nboom\n"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def make_fns(jobs_by_scope: dict, outputs: dict, contents: dict):
    """构造注入 helper：list_jobs / list_job_outputs / get_job_output。"""

    def list_jobs_fn(scope: str):
        return jobs_by_scope.get(scope, [])

    def list_outputs_fn(scope: str, job_id: str, lim: int):
        return outputs.get((scope, job_id), [])[:lim]

    def get_output_fn(scope: str, job_id: str, output_id: str):
        if output_id in contents:
            return {"content": contents[output_id]}
        return None

    return list_jobs_fn, list_outputs_fn, get_output_fn


# ---------------------------------------------------------------------------
# _parse_job_id
# ---------------------------------------------------------------------------
def test_parse_job_id_profile_and_kind() -> None:
    assert _parse_job_id("mxai-wechat-scheduled_touch") == ("wechat", "scheduled_touch")
    assert _parse_job_id("mxai-douyin-benchmark_monitor") == ("douyin", "benchmark_monitor")
    assert _parse_job_id("mxai-shipinhao-first_comment_daily") == (
        "shipinhao",
        "first_comment_daily",
    )


def test_parse_job_id_maintenance_to_system() -> None:
    assert _parse_job_id("mxai-maintenance") == ("system", "maintenance")
    assert _parse_job_id("mxai-default-maintenance") == ("system", "maintenance")


def test_parse_job_id_rejects_non_whitelist() -> None:
    assert _parse_job_id("hermes-daily-report") is None
    assert _parse_job_id("mxai-wechat-no_agent") is None
    assert _parse_job_id("mxai-scheduled_touch") is None  # 缺 profile 段
    assert _parse_job_id("") is None


# ---------------------------------------------------------------------------
# _derive_record_status
# ---------------------------------------------------------------------------
def test_derive_status_ok_via_callback_success_true() -> None:
    assert _derive_record_status(content_ok(), NOW - timedelta(minutes=1), NOW) == "ok"


def test_derive_status_failed_via_callback_success_false() -> None:
    assert _derive_record_status(content_fail_callback(), NOW, NOW) == "failed"


def test_derive_status_failed_via_http_failed_marker() -> None:
    assert _derive_record_status(content_fail_http(), NOW, NOW) == "failed"


def test_derive_status_running_within_grace() -> None:
    run_dt = NOW - timedelta(seconds=RUNNING_GRACE_SECONDS - 60)
    assert _derive_record_status(content_running(), run_dt, NOW) == "running"


def test_derive_status_failed_when_running_over_grace() -> None:
    run_dt = NOW - timedelta(seconds=RUNNING_GRACE_SECONDS + 60)
    assert _derive_record_status(content_running(), run_dt, NOW) == "failed"


# ---------------------------------------------------------------------------
# _aggregate_cron_records
# ---------------------------------------------------------------------------
def test_aggregate_merge_sort_and_pagination() -> None:
    profile_dicts = [{"name": "wechat"}, {"name": "douyin"}]
    jobs = {
        "wechat": [{"id": "mxai-wechat-scheduled_touch"}],
        "douyin": [{"id": "mxai-douyin-benchmark_monitor"}],
    }
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w2", "run_at": _iso(NOW - timedelta(minutes=1)), "status": "ok"},
            {"output_id": "w1", "run_at": _iso(NOW - timedelta(minutes=30)), "status": "ok"},
        ],
        ("douyin", "mxai-douyin-benchmark_monitor"): [
            {"output_id": "d1", "run_at": _iso(NOW - timedelta(minutes=10)), "status": "ok"},
        ],
    }
    contents = {"w2": content_ok(), "w1": content_ok(), "d1": content_ok()}
    fns = make_fns(jobs, outputs, contents)
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, page=1, page_size=2)
    ids = [r["output_id"] for r in res["records"]]
    assert ids == ["w2", "d1"]  # 倒序合并 + 首页 2 条
    assert res["total"] == 3
    assert res["page"] == 1
    assert res["page_size"] == 2
    assert res["today_count"] == 3


def test_aggregate_pagination_page_two() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": f"o{i}", "run_at": _iso(NOW - timedelta(minutes=i)), "status": "ok"}
            for i in range(1, 8)  # 7 条，o1(最新)..o7(最旧)
        ]
    }
    contents = {f"o{i}": content_ok() for i in range(1, 8)}
    fns = make_fns(jobs, outputs, contents)

    p1 = _aggregate_cron_records(profile_dicts, *fns, now=NOW, page=1, page_size=5)
    assert [r["output_id"] for r in p1["records"]] == ["o1", "o2", "o3", "o4", "o5"]
    assert p1["total"] == 7

    p2 = _aggregate_cron_records(profile_dicts, *fns, now=NOW, page=2, page_size=5)
    assert [r["output_id"] for r in p2["records"]] == ["o6", "o7"]
    assert p2["total"] == 7
    assert p2["page"] == 2

    p3 = _aggregate_cron_records(profile_dicts, *fns, now=NOW, page=3, page_size=5)
    assert p3["records"] == []  # 超范围页 → 空、total 不变
    assert p3["total"] == 7


def test_aggregate_page_size_cap_200() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outputs = {("wechat", "mxai-wechat-scheduled_touch"): []}
    fns = make_fns(jobs, outputs, {})
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, page_size=9999)
    assert res["page_size"] == 200  # 上限裁剪


def test_aggregate_profile_filter() -> None:
    profile_dicts = [{"name": "wechat"}, {"name": "douyin"}]
    jobs = {
        "wechat": [{"id": "mxai-wechat-scheduled_touch"}],
        "douyin": [{"id": "mxai-douyin-benchmark_monitor"}],
    }
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w1", "run_at": _iso(NOW - timedelta(minutes=1)), "status": "ok"},
        ],
        ("douyin", "mxai-douyin-benchmark_monitor"): [
            {"output_id": "d1", "run_at": _iso(NOW - timedelta(minutes=2)), "status": "ok"},
        ],
    }
    contents = {"w1": content_ok(), "d1": content_ok()}
    fns = make_fns(jobs, outputs, contents)
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, profile="wechat")
    assert [r["profile"] for r in res["records"]] == ["wechat"]
    assert res["records"][0]["profile_label"] == "个人微信"


def test_aggregate_status_filter_each() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "ok1", "run_at": _iso(NOW - timedelta(minutes=1)), "status": "ok"},
            {"output_id": "run1", "run_at": _iso(NOW - timedelta(minutes=2)), "status": "ok"},
            {"output_id": "fail1", "run_at": _iso(NOW - timedelta(minutes=3)), "status": "failed"},
        ]
    }
    contents = {
        "ok1": content_ok(),
        "run1": content_running(),
        # fail1 走 status==failed 短路，不读全文
    }
    fns = make_fns(jobs, outputs, contents)

    ok_res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, status="ok")
    assert [r["output_id"] for r in ok_res["records"]] == ["ok1"]

    run_res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, status="running")
    assert [r["output_id"] for r in run_res["records"]] == ["run1"]
    assert run_res["running_count"] == 1

    fail_res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, status="failed")
    assert [r["output_id"] for r in fail_res["records"]] == ["fail1"]

    multi = _aggregate_cron_records(profile_dicts, *fns, now=NOW, status="ok,failed")
    assert {r["output_id"] for r in multi["records"]} == {"ok1", "fail1"}


def test_aggregate_range_windows() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "today", "run_at": _iso(NOW - timedelta(hours=1)), "status": "ok"},
            {"output_id": "d3", "run_at": _iso(NOW - timedelta(days=3)), "status": "ok"},
            {"output_id": "d10", "run_at": _iso(NOW - timedelta(days=10)), "status": "ok"},
        ]
    }
    contents = {"today": content_ok(), "d3": content_ok(), "d10": content_ok()}
    fns = make_fns(jobs, outputs, contents)

    today_res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, range_="today")
    assert [r["output_id"] for r in today_res["records"]] == ["today"]

    week_res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, range_="7d")
    assert {r["output_id"] for r in week_res["records"]} == {"today", "d3"}

    custom = _aggregate_cron_records(
        profile_dicts,
        *fns,
        now=NOW,
        range_="custom",
        start="2026-07-01",
        end="2026-07-02",
    )
    assert [r["output_id"] for r in custom["records"]] == ["d3"]  # 7-2 落在 [7-01,7-03)


def test_aggregate_maintenance_maps_to_system() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {
        "wechat": [{"id": "mxai-wechat-scheduled_touch"}],
        "default": [{"id": "mxai-maintenance"}],
    }
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w1", "run_at": _iso(NOW - timedelta(minutes=5)), "status": "ok"},
        ],
        ("default", "mxai-maintenance"): [
            {"output_id": "m1", "run_at": _iso(NOW - timedelta(minutes=1)), "status": "ok"},
        ],
    }
    contents = {"w1": content_ok(), "m1": content_ok("【全局维护·日报整理】 已执行")}
    fns = make_fns(jobs, outputs, contents)
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW, profile="system")
    assert len(res["records"]) == 1
    rec = res["records"][0]
    assert rec["profile"] == "system"
    assert rec["profile_label"] == "全局维护"
    assert rec["kind"] == "maintenance"
    assert rec["kind_label"] == "全局维护·日报整理"


def test_aggregate_excludes_non_mxai_and_non_whitelist_jobs() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {
        "wechat": [
            {"id": "mxai-wechat-scheduled_touch"},
            {"id": "mxai-wechat-no_agent"},  # kind 非白名单
            {"id": "hermes-daily-digest"},  # 非 mxai 前缀
        ]
    }
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w1", "run_at": _iso(NOW - timedelta(minutes=1)), "status": "ok"},
        ],
        ("wechat", "mxai-wechat-no_agent"): [
            {"output_id": "n1", "run_at": _iso(NOW), "status": "ok"},
        ],
        ("wechat", "hermes-daily-digest"): [
            {"output_id": "h1", "run_at": _iso(NOW), "status": "ok"},
        ],
    }
    contents = {"w1": content_ok(), "n1": content_ok(), "h1": content_ok()}
    fns = make_fns(jobs, outputs, contents)
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW)
    assert [r["job_id"] for r in res["records"]] == ["mxai-wechat-scheduled_touch"]


def test_aggregate_summary_from_message_truncates() -> None:
    profile_dicts = [{"name": "wechat"}]
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    long_msg = "触达" * 200
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w1", "run_at": _iso(NOW), "status": "ok", "preview": "p"},
        ]
    }
    contents = {"w1": content_ok(long_msg)}
    fns = make_fns(jobs, outputs, contents)
    res = _aggregate_cron_records(profile_dicts, *fns, now=NOW)
    summary = res["records"][0]["summary"]
    assert summary.endswith("…")
    assert len(summary) <= 201


# ---------------------------------------------------------------------------
# 集成：GET /api/plugins/mxai/cron/records
# ---------------------------------------------------------------------------
def _patch_helpers(monkeypatch, jobs_by_scope, outputs, contents) -> None:
    import hermes_cli.web_routes.cron as hcron

    def fake_call(scope, func, *args, **kwargs):
        if func == "list_jobs":
            return jobs_by_scope.get(scope, [])
        if func == "list_job_outputs":
            return outputs.get((scope, args[0]), [])
        if func == "get_job_output":
            oid = args[1]
            return {"content": contents[oid]} if oid in contents else None
        return None

    monkeypatch.setattr(hcron, "_cron_profile_dicts", lambda: [{"name": "wechat"}])
    monkeypatch.setattr(hcron, "_call_cron_for_profile", fake_call)


def test_endpoint_shape_and_readonly_no_token(mxai_client: TestClient, monkeypatch) -> None:
    from hermes_time import now as hnow

    run_at = hnow().isoformat()
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outputs = {
        ("wechat", "mxai-wechat-scheduled_touch"): [
            {"output_id": "w1", "run_at": run_at, "status": "ok"},
        ]
    }
    contents = {"w1": content_ok()}
    _patch_helpers(monkeypatch, jobs, outputs, contents)

    # 缺 token：与其它 mxai 只读端点一致（fixture 不过门），返回 200。
    res = mxai_client.get("/api/plugins/mxai/cron/records")
    assert res.status_code == 200
    body = res.json()
    assert set(body) >= {"records", "total", "page", "page_size", "today_count", "running_count", "range"}
    assert body["range"] == "today"
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total"] == 1
    assert len(body["records"]) == 1
    rec = body["records"][0]
    assert rec["profile"] == "wechat"
    assert rec["profile_label"] == "个人微信"
    assert rec["kind_label"] == "定时触达"
    assert rec["status"] == "ok"
    assert body["today_count"] == 1


def test_endpoint_pagination_params(mxai_client: TestClient, monkeypatch) -> None:
    from hermes_time import now as hnow

    base = hnow()
    jobs = {"wechat": [{"id": "mxai-wechat-scheduled_touch"}]}
    outs = [
        {"output_id": f"o{i}", "run_at": (base - timedelta(minutes=i)).isoformat(), "status": "ok"}
        for i in range(1, 8)
    ]
    outputs = {("wechat", "mxai-wechat-scheduled_touch"): outs}
    contents = {f"o{i}": content_ok() for i in range(1, 8)}
    _patch_helpers(monkeypatch, jobs, outputs, contents)

    res = mxai_client.get("/api/plugins/mxai/cron/records?page=2&page_size=5")
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 7
    assert [r["output_id"] for r in body["records"]] == ["o6", "o7"]
