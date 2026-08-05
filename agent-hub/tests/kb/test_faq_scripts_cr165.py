"""CR-165：FAQ/话术分区种子、匹配、Excel 导入导出。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from plugins.mxai.kb.faq_scripts import (
    add_faq_entry,
    export_faq_excel,
    import_faq_excel,
    match_faq_scripts_reply,
)
from plugins.mxai.kb.partition_scope import (
    FAQ_SCRIPTS_PARTITION_NAME,
    get_faq_scripts_partition,
    resolve_allowed_partition_ids,
)
from plugins.mxai.kb.service import BUSINESS_PARTITIONS, ensure_business_partitions, list_partitions


def test_seed_includes_faq_scripts(tmp_path: Path) -> None:
    ensure_business_partitions(tmp_path)
    names = [p["name"] for p in list_partitions(tmp_path)]
    assert FAQ_SCRIPTS_PARTITION_NAME in names
    assert any(n == FAQ_SCRIPTS_PARTITION_NAME for n, _e, _o in BUSINESS_PARTITIONS)
    part = get_faq_scripts_partition(data_dir=tmp_path)
    assert part is not None
    assert part["enabled"] is True


def test_upgrade_adds_missing_faq_partition(tmp_path: Path) -> None:
    """存量五分区库应补种 FAQ/话术。"""
    from plugins.mxai.kb.service import _db
    from plugins.mxai.kb.storage.kb_repo import init_kb_schema
    import sqlite3

    init_kb_schema(_db(tmp_path))
    conn = sqlite3.connect(_db(tmp_path))
    try:
        for pid, (name, enabled, sort_order) in enumerate(
            [
                ("产品业务分区", 1, 1),
                ("售后答疑分区", 1, 2),
                ("报价方案分区", 1, 3),
                ("招聘话术分区", 1, 4),
                ("风控合规分区", 0, 5),
            ],
            start=1,
        ):
            conn.execute(
                "INSERT INTO kb_partitions (partition_id, name, enabled, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (pid, name, enabled, sort_order),
            )
        conn.commit()
    finally:
        conn.close()

    n = ensure_business_partitions(tmp_path)
    assert n >= 1
    assert get_faq_scripts_partition(data_dir=tmp_path) is not None


def test_match_and_excel_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plugins.mxai.kb.storage.kb_repo import init_kb_schema
    from plugins.mxai.cfg.paths import mxai_db_path
    from plugins.mxai.kb.worker import KbWorker

    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    ensure_business_partitions(data_dir)
    part = get_faq_scripts_partition(data_dir=data_dir)
    assert part
    pid = int(part["partition_id"])

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["question", "answer"])
    ws.append(["你们支持本地部署吗", "支持本地私有化部署。"])
    ws.append(["能离线用吗", "支持本地私有化部署。"])
    buf = io.BytesIO()
    wb.save(buf)
    res = import_faq_excel(pid, buf.getvalue(), data_dir=data_dir)
    assert res["imported"] >= 1

    # agent=None：仅测分区 enabled（避免读本机 cfg 干扰 tmp 库）
    hit = match_faq_scripts_reply(
        "你们支持本地部署吗", agent=None, data_dir=data_dir
    )
    assert hit is not None
    assert "本地" in hit["text"]
    assert hit["match"] == "exact"

    allowed = resolve_allowed_partition_ids(None, data_dir=data_dir)
    assert pid in allowed

    raw = export_faq_excel(pid, data_dir=data_dir)
    assert len(raw) > 100


def _faq_hub_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from plugins.mxai.kb.storage.kb_repo import init_kb_schema
    from plugins.mxai.cfg.paths import mxai_db_path
    from plugins.mxai.kb.worker import KbWorker

    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    ensure_business_partitions(data_dir)
    return data_dir


def test_add_faq_entry_single(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _faq_hub_tmp(tmp_path, monkeypatch)
    part = get_faq_scripts_partition(data_dir=data_dir)
    assert part
    pid = int(part["partition_id"])

    item = add_faq_entry(
        pid,
        ["鼻炎膏有用吗", "怎么卖"],
        "系统弹出引导留资话术。",
        data_dir=data_dir,
    )
    assert item["doc_id"]
    assert item["chunk_id"]
    assert item["intent_phrases"] == ["鼻炎膏有用吗", "怎么卖"]

    hit = match_faq_scripts_reply("鼻炎膏有用吗", agent=None, data_dir=data_dir)
    assert hit is not None
    assert "引导留资" in hit["text"]


def test_add_faq_entry_rejects_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _faq_hub_tmp(tmp_path, monkeypatch)
    part = get_faq_scripts_partition(data_dir=data_dir)
    pid = int(part["partition_id"])
    with pytest.raises(ValueError, match="常见问法"):
        add_faq_entry(pid, [], "有答无问", data_dir=data_dir)
    with pytest.raises(ValueError, match="正文"):
        add_faq_entry(pid, ["有问"], "  ", data_dir=data_dir)
    with pytest.raises(ValueError, match="仅支持"):
        add_faq_entry(1, ["问"], "答", data_dir=data_dir)
