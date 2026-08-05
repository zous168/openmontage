"""业务知识库分区首启初始化（ensure_business_partitions）。"""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.kb.service import (
    BUSINESS_PARTITIONS,
    ensure_business_partitions,
    ensure_default_partition,
    list_partitions,
)


def test_ensure_business_partitions_on_empty_db(tmp_path: Path) -> None:
    n = ensure_business_partitions(tmp_path)
    assert n == len(BUSINESS_PARTITIONS)
    parts = list_partitions(tmp_path)
    names = [p["name"] for p in parts]
    assert names == [name for name, _en, _ord in BUSINESS_PARTITIONS]
    # 幂等：再次调用不重复写入
    assert ensure_business_partitions(tmp_path) == 0
    assert len(list_partitions(tmp_path)) == len(BUSINESS_PARTITIONS)


def test_ensure_business_partitions_upgrades_empty_default(tmp_path: Path) -> None:
    ensure_default_partition(tmp_path)
    parts = list_partitions(tmp_path)
    assert len(parts) == 1
    assert parts[0]["name"] == "default"

    n = ensure_business_partitions(tmp_path)
    assert n == len(BUSINESS_PARTITIONS)
    names = [p["name"] for p in list_partitions(tmp_path)]
    assert "default" not in names
    assert "产品业务分区" in names
