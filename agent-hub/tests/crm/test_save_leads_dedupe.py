"""P0-1 · save_leads 带 douyin_id 时走 insert_comment_lead 去重."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.crm.lead_service import get_lead, insert_comment_lead, save_leads
from plugins.mxai.rpa.types import CollectedComment


@pytest.fixture
def lead_env(tmp_path: Path) -> Path:
    return tmp_path / "hub"


def test_save_leads_with_douyin_id_dedupes(lead_env: Path) -> None:
    first = insert_comment_lead(
        profile_id="douyin",
        nickname="甲",
        douyin_id="dy_001",
        comment="第一次",
        intent="高",
        data_dir=lead_env,
    )
    ids = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[
            CollectedComment(
                comment_id="c2",
                author="甲",
                text="第二次",
                video_id="v1",
                keyword="挖掘机",
                douyin_id="dy_001",
            )
        ],
        data_dir=lead_env,
    )
    assert ids == []
    lead = get_lead(lead_id=first["lead_id"], data_dir=lead_env)
    assert lead is not None
    assert lead["source_comment"] == "第一次"


def test_save_leads_with_douyin_id_inserts_new(lead_env: Path) -> None:
    ids = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[
            CollectedComment(
                comment_id="c1",
                author="乙",
                text="询价",
                video_id="v2",
                keyword="工程机械",
                douyin_id="dy_new",
            )
        ],
        data_dir=lead_env,
    )
    assert len(ids) == 1
    lead = get_lead(lead_id=ids[0], data_dir=lead_env)
    assert lead["douyin_id"] == "dy_new"
