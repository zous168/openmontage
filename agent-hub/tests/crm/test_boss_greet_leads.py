"""CR-147 · boss_greet_lead 登记与门闸."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.crm.boss_greet_leads import (
    BossGreetLeadDuplicateError,
    gate_label_for_lead,
    get_greet_lead,
    is_boss_position_peer,
    is_eligible_for_proactive_dm,
    leads_as_candidates,
    list_eligible_for_proactive_dm,
    list_known_boss_positions,
    normalize_boss_text,
    register_greet_lead,
    touch_last_inbound,
    increment_proactive_dm,
)


@pytest.fixture
def lead_env(tmp_path: Path) -> Path:
    return tmp_path / "hub"


def test_normalize_boss_text_strips_all_whitespace() -> None:
    assert normalize_boss_text("张 三") == "张三"
    assert normalize_boss_text("Java\u3000工程师") == "Java工程师"


def test_register_and_duplicate(lead_env: Path) -> None:
    row = register_greet_lead(
        "boss",
        name="张 三",
        reason="简历匹配度高",
        position="Java工程师",
        data_dir=lead_env,
    )
    assert row["display_name"] == "张三"
    assert row["position"] == "Java工程师"
    assert row["match_reason"] == "简历匹配度高"
    assert row["greet_registered_at"] == row["last_inbound_at"]
    with pytest.raises(BossGreetLeadDuplicateError):
        register_greet_lead("boss", name="张三", reason="其它", data_dir=lead_env)


def test_format_greet_op_object() -> None:
    from plugins.mxai.crm.boss_greet_leads import format_greet_op_object

    assert format_greet_op_object("张三", "Java工程师", "简历匹配") == "张三 · Java工程师 · 简历匹配"


def test_inbound_touch_breaks_eligibility(lead_env: Path) -> None:
    register_greet_lead("boss", name="李四", reason="测试", position="测试岗", data_dir=lead_env)
    assert touch_last_inbound("boss", "李 四", at="2026-07-09T12:00:00+00:00", data_dir=lead_env)
    lead = get_greet_lead("boss", "李四", data_dir=lead_env)
    assert lead is not None
    assert not is_eligible_for_proactive_dm(lead)
    assert gate_label_for_lead(lead) == "已监听停发"
    assert list_eligible_for_proactive_dm("boss", data_dir=lead_env) == []


def test_proactive_dm_count_cap(lead_env: Path) -> None:
    register_greet_lead("boss", name="王五", reason="匹配", position="PM", data_dir=lead_env)
    for _ in range(5):
        increment_proactive_dm("boss", "王五", data_dir=lead_env)
    lead = get_greet_lead("boss", "王五", data_dir=lead_env)
    assert lead is not None
    assert lead["proactive_dm_count"] == 4
    assert gate_label_for_lead(lead) == "已满4次"


def test_leads_as_candidates_and_position_peer(lead_env: Path) -> None:
    register_greet_lead(
        "boss",
        name="赵六",
        reason="匹配",
        position="新媒体销售专员",
        data_dir=lead_env,
    )
    items = leads_as_candidates(
        [get_greet_lead("boss", "赵六", data_dir=lead_env) or {}],
        limit=10,
    )
    assert len(items) == 1
    assert items[0]["id"] == "赵六"
    assert items[0]["job"] == "新媒体销售专员"
    known = list_known_boss_positions("boss", data_dir=lead_env, extra_positions=["Java工程师"])
    assert "新媒体销售专员" in known
    assert "Java工程师" in known
    assert is_boss_position_peer("新媒体销售专员", data_dir=lead_env, positions=known)
    assert not is_boss_position_peer("赵六", data_dir=lead_env, positions=known)


def test_register_rejects_name_equals_position(lead_env: Path) -> None:
    with pytest.raises(ValueError, match="not position"):
        register_greet_lead(
            "boss",
            name="新媒体销售专员",
            reason="误识别",
            position="新媒体销售专员",
            data_dir=lead_env,
        )


def test_leads_as_candidates_skips_name_equals_position(lead_env: Path) -> None:
    # 绕过 register 门禁直接造脏行
    from plugins.mxai.crm.boss_greet_leads import _conn, _utc_now_iso
    from plugins.mxai.storage.channel_tables import BOSS_GREET_TABLE

    now = _utc_now_iso()
    with _conn(lead_env) as conn:
        conn.execute(
            f"""
            INSERT INTO {BOSS_GREET_TABLE} (
                display_name, channel_account_id, position, match_reason,
                greet_registered_at, last_inbound_at, proactive_dm_count,
                created_at, updated_at
            ) VALUES (?, 'single-account-default', ?, ?, ?, ?, 0, ?, ?)
            """,
            ("新媒体销售专员", "新媒体销售专员", "x", now, now, now, now),
        )
        conn.commit()
    items = leads_as_candidates(
        [get_greet_lead("boss", "新媒体销售专员", data_dir=lead_env) or {}],
        limit=10,
    )
    assert items == []
