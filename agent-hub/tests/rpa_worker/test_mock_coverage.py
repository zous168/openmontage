"""LT-030.04.01/04.02 — mock 客户端协议同步 + 全 task_type 覆盖契约.

跨仓加载 automan mock-rpa-cli 的 mock_results / mock_worker 与 hub_worker message_types，
断言：① 渠道三方一致（单一事实源）② CLI mock 覆盖 hub **全部**已注册 task_type（非降级）。
数量随 hub `_HANDLERS` 增长（CR-169 起含 video_comment），断言按注册表动态取。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plugins.mxai.orchestrator.task_handlers import _HANDLERS

_AUTOMAN = Path(__file__).resolve().parents[3] / "automan"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_cli = _load("am_mock_worker", _AUTOMAN / "mock-rpa-cli" / "mock_worker.py")
_results = _load("am_mock_results", _AUTOMAN / "mock-rpa-cli" / "mock_results.py")
_mt = _load("am_hub_worker_mt", _AUTOMAN / "src" / "hub_worker" / "message_types.py")

# hub 期望的全部 task_type（task_handlers 注册表；数量随需求增长）
HUB_TASK_TYPES = set(_HANDLERS.keys())


# ── 04.01 协议同步：渠道单一事实源 ────────────────────────
def test_channels_aligned_across_three_sources():
    cli = set(_cli.CHANNELS)
    mt = set(_mt.CHANNELS)
    expected = {"douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss"}
    assert cli == expected, f"CLI mock channels drift: {cli}"
    assert mt == expected, f"hub_worker channels drift: {mt}"
    assert cli == mt, "CLI mock 与 hub_worker channels 不一致"


def test_message_types_constants_present():
    # hub_worker 协议常量齐全（worker 基准）
    assert _mt.ROLE_RPA_WORKER == "rpa_worker"
    for c in ("MSG_HELLO", "MSG_HELLO_ACK", "MSG_TASK_DISPATCH", "MSG_TASK_RESULT",
              "MSG_PING", "MSG_PONG", "STATUS_SUCCEEDED", "STATUS_FAILED"):
        assert hasattr(_mt, c), f"缺协议常量 {c}"


# ── 04.02 功能完善：15 task_type 全覆盖（非降级）───────────
def _payload_for(tt: str) -> dict:
    return {
        "lead_ids": ["lead_1"], "contacts": ["c1", "c2"], "keywords": ["kw"],
        "benchmarks": ["bm1"], "candidates": ["cand1"], "recipient": "u1",
        "message": "hi", "file_path": "/tmp/x", "scripts": ["s1"],
    }


def test_cli_mock_covers_all_task_types():
    missing = []
    for tt in sorted(HUB_TASK_TYPES):
        r = _results.build_mock_result(
            {"task_type": tt, "profile_id": "wechat", "name": tt, "payload": _payload_for(tt)},
        )
        # 非降级：不应回退到 simulated 兜底
        if r.get("simulated") is True:
            missing.append(tt)
    assert not missing, f"CLI mock 未覆盖（仍降级 simulated）: {missing}"


def test_cli_mock_shapes_match_handlers():
    # 抽样关键 task_type 的 result 形状
    def res(tt, payload):
        return _results.build_mock_result(
            {"task_type": tt, "profile_id": "douyin", "name": tt, "payload": payload})

    cr = res("comment_reply", {"lead_ids": ["L1", "L2"]})
    assert "results" in cr and cr["replied"] == 2 and "skipped_leads" in cr

    fc = res("first_comment", {"benchmarks": ["b1", "b2"]})
    assert fc["posted"] == 2 and "posts" in fc and "scripts" in fc

    bm = res("benchmark", {"benchmark_ids": ["x"]})
    assert "collected" in bm and "lead_ids" in bm

    sf = res("send_file", {"recipient": "u1", "file_path": "/f"})
    assert sf["sent"] is True

    ac = res("add_contacts", {"contacts": ["a", "b", "c"]})
    assert ac["total"] == 3


def test_cli_mock_uses_hub_reply_when_present():
    # 回复类：hub 预算回复优先（与 Vue mock 协议一致）
    r = _results.build_mock_result(
        {"task_type": "dm", "profile_id": "wechat", "name": "dm",
         "payload": {"recipient": "u1", "hub_reply": {"text": "hub 预算回复", "source": "kb"}}},
    )
    assert r["reply"]["text"] == "hub 预算回复"
    assert r["reply"]["source"] == "kb"
