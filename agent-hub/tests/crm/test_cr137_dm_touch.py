"""CR-137 · dm_touch_status / funnel / bootstrap payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.crm.funnel import apply_funnel_from_task
from plugins.mxai.crm.lead_service import get_lead, insert_comment_lead, list_lead_ids_pending_dm, record_dm_sent
from plugins.mxai.orchestrator.bootstrap_public import bootstrap_dm_touch
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager


@pytest.fixture
def dm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    profiles = data_dir / "profiles" / "douyin"
    profiles.mkdir(parents=True)
    (profiles / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (profiles / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    # CR-145：hub.db 等已收口 plugins/mxai/data，路径解析改经 cfg.paths（env-first）；
    # 仅 scheduler.state 保留 resolve_ 符号供替身，其余模块 setenv(HUB_DATA_DIR) 已足够。
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"dm": {"auto_enabled": True, "message": "固定话术"}},
    )
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    return data_dir


def test_list_pending_dm_fifo(dm_env: Path) -> None:
    insert_comment_lead(
        profile_id="douyin", nickname="b", douyin_id="id_b",
        comment="c2", intent="低", time_iso="2026-01-02T00:00:00+00:00", data_dir=dm_env,
    )
    insert_comment_lead(
        profile_id="douyin", nickname="a", douyin_id="id_a",
        comment="c1", intent="高", time_iso="2026-01-01T00:00:00+00:00", data_dir=dm_env,
    )
    ids = list_lead_ids_pending_dm("douyin", data_dir=dm_env)
    assert ids[0] == get_lead(lead_id=ids[0], data_dir=dm_env)["lead_id"]
    first = get_lead(lead_id=ids[0], data_dir=dm_env)
    assert first["douyin_id"] == "id_a"


def test_apply_funnel_dm_marks_sent(dm_env: Path) -> None:
    r = insert_comment_lead(
        profile_id="douyin", nickname="u", douyin_id="20390981",
        comment="询价", intent="高", data_dir=dm_env,
    )
    lead_id = r["lead_id"]
    apply_funnel_from_task(
        "douyin",
        "dm",
        {"recipient": "20390981", "message": "你好", "lead_id": lead_id},
        {"send": {"sent": True}, "recipient": "20390981"},
        data_dir=dm_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=dm_env)
    assert lead["funnel_stage"] == "dm_reached"
    assert lead["dm_touch_status"] == "sent"


def test_apply_funnel_dm_marks_sent_via_send_status(dm_env: Path) -> None:
    """生产 AutoMan 回执：顶层 send_status=sent（无嵌套 send.sent）."""
    r = insert_comment_lead(
        profile_id="douyin", nickname="u_ss", douyin_id="72725662157",
        comment="询价", intent="高", data_dir=dm_env,
    )
    lead_id = r["lead_id"]
    apply_funnel_from_task(
        "douyin",
        "dm",
        {"recipient": "72725662157", "message": "你好", "lead_id": lead_id},
        {"send_status": "sent", "mode": "automan"},
        data_dir=dm_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=dm_env)
    assert lead["funnel_stage"] == "dm_reached"
    assert lead["dm_touch_status"] == "sent"
    assert list_lead_ids_pending_dm("douyin", data_dir=dm_env) == []


def test_apply_funnel_dm_automan_succeeded_empty_outputs(dm_env: Path) -> None:
    """douyin_sendmsg 常无 send_status：from_result 按工作流成功归一后再入漏斗."""
    from plugins.mxai.rpa_worker.automan_bridge import from_result

    r = insert_comment_lead(
        profile_id="douyin", nickname="u_empty", douyin_id="dy_empty_ok",
        comment="c", intent="高", data_dir=dm_env,
    )
    lead_id = r["lead_id"]
    result = from_result("dm", {}, workflow_status="succeeded")
    apply_funnel_from_task(
        "douyin",
        "dm",
        {"recipient": "dy_empty_ok", "message": "你好", "lead_id": lead_id},
        result,
        data_dir=dm_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=dm_env)
    assert lead["dm_touch_status"] == "sent"


def test_recipient_without_sent_does_not_mark_dm(dm_env: Path) -> None:
    r = insert_comment_lead(
        profile_id="douyin", nickname="u2", douyin_id="99887766",
        comment="询价", intent="高", data_dir=dm_env,
    )
    lead_id = r["lead_id"]
    apply_funnel_from_task(
        "douyin",
        "dm",
        {"recipient": "99887766", "message": "你好", "lead_id": lead_id},
        {"recipient": "99887766"},
        data_dir=dm_env,
    )
    lead = get_lead(lead_id=lead_id, data_dir=dm_env)
    assert lead["funnel_stage"] != "dm_reached"
    assert lead["dm_touch_status"] == "not_sent"


def test_apply_funnel_dm_not_sent_keeps_pending(dm_env: Path) -> None:
    r = insert_comment_lead(
        profile_id="douyin", nickname="u3", douyin_id="dy_not",
        comment="c", intent="高", data_dir=dm_env,
    )
    lead_id = r["lead_id"]
    apply_funnel_from_task(
        "douyin",
        "dm",
        {"recipient": "dy_not", "message": "你好", "lead_id": lead_id},
        {"send_status": "not_sent", "mode": "automan"},
        data_dir=dm_env,
    )
    assert get_lead(lead_id=lead_id, data_dir=dm_env)["dm_touch_status"] == "not_sent"
    assert lead_id in list_lead_ids_pending_dm("douyin", data_dir=dm_env)

def test_bootstrap_uses_douyin_id_not_author(dm_env: Path) -> None:
    insert_comment_lead(
        profile_id="douyin", nickname="昵称A", douyin_id="dy_bootstrap_only",
        comment="c", intent="高", data_dir=dm_env,
    )
    rows = bootstrap_dm_touch("douyin")
    assert len(rows) == 1
    task = QueueManager.get()._tasks[rows[0]["task_id"]]
    assert task.payload["recipient"] == "dy_bootstrap_only"
    assert task.payload["message"] == "固定话术"


def test_record_dm_sent_idempotent(dm_env: Path) -> None:
    r = insert_comment_lead(
        profile_id="douyin", nickname="x", douyin_id="dy_x",
        comment="c", intent="高", data_dir=dm_env,
    )
    record_dm_sent(r["lead_id"], data_dir=dm_env)
    assert get_lead(lead_id=r["lead_id"], data_dir=dm_env)["dm_touch_status"] == "sent"
    assert list_lead_ids_pending_dm("douyin", data_dir=dm_env) == []


def test_normalize_dm_payload_maps_nickname_to_douyin_id(dm_env: Path) -> None:
    from plugins.mxai.crm.lead_service import normalize_dm_payload

    insert_comment_lead(
        profile_id="douyin", nickname="wdlceshi", douyin_id="11ww1",
        comment="nihao", intent="高", data_dir=dm_env,
    )
    out = normalize_dm_payload(
        "douyin",
        {"recipient": "wdlceshi", "message": "你好"},
        data_dir=dm_env,
    )
    assert out["recipient"] == "11ww1"
    assert out.get("lead_id")
