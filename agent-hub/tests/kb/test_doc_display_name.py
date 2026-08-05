"""知识库文档展示名."""

from __future__ import annotations

from plugins.mxai.kb.service import doc_display_name


def test_doc_display_name_windows_path() -> None:
    assert doc_display_name(r"C:\ProgramData\MarketingHub\shared\knowledge\automan-agent.log") == "automan-agent.log"


def test_doc_display_name_relative_path() -> None:
    assert doc_display_name("demo/产品介绍手册.pdf") == "产品介绍手册.pdf"


def test_doc_display_name_inline() -> None:
    assert doc_display_name("inline:FAQ 条目") == "FAQ 条目"


def test_doc_display_name_fallback() -> None:
    assert doc_display_name("", fallback="doc_abc") == "doc_abc"
