"""批量添加 Excel 模板生成."""

from __future__ import annotations

from plugins.mxai.contacts.pending_add_template import (
    build_pending_add_template_xlsx,
    contact_column_header,
)
from plugins.mxai.contacts.structured_parser import parse_structured_file


def test_headers_by_profile() -> None:
    assert contact_column_header("wechat") == "微信号"
    assert contact_column_header("qiyeweixin") == "企业微信号"


def test_wechat_template_roundtrip() -> None:
    raw = build_pending_add_template_xlsx("wechat")
    assert raw[:2] == b"PK"  # zip/xlsx
    parsed = parse_structured_file(raw, "批量添加好友模板.xlsx")
    assert len(parsed.rows) == 2
    assert parsed.rows[0].display_name == "示例客户"
    assert parsed.rows[0].contact_id == "wxid_example"
    assert parsed.rows[1].contact_id == "13800000001"


def test_wecom_template_header() -> None:
    raw = build_pending_add_template_xlsx("qiyeweixin")
    parsed = parse_structured_file(raw, "批量添加客户模板.xlsx")
    assert parsed.rows[0].contact_id == "wxid_example"
