"""CR-91 comment_keywords cfg helpers."""

from __future__ import annotations

from plugins.mxai.cfg.comment_keywords import (
    filter_comments_by_match,
    matches_comment,
    parse_comment_keywords,
)
from plugins.mxai.rpa.types import CollectedComment


def test_parse_legacy_keywords_as_search() -> None:
    parsed = parse_comment_keywords({"keywords": [" 挖掘机 ", ""]})
    assert parsed["search_keywords"] == ["挖掘机"]
    assert parsed["match_keywords"] == []


def test_parse_dual_fields() -> None:
    parsed = parse_comment_keywords(
        {"search_keywords": ["工程机械"], "match_keywords": ["多少钱"]}
    )
    assert parsed["search_keywords"] == ["工程机械"]
    assert parsed["match_keywords"] == ["多少钱"]


def test_filter_comments_by_match() -> None:
    comments = [
        CollectedComment("1", "u1", "路过看看", "v1", "kw"),
        CollectedComment("2", "u2", "培训多少钱", "v1", "kw"),
    ]
    matched = filter_comments_by_match(comments, ["多少钱"])
    assert len(matched) == 1
    assert matched[0].author == "u2"


def test_empty_match_keywords_keeps_all() -> None:
    comments = [CollectedComment("1", "u1", "任意", "v1", "kw")]
    assert filter_comments_by_match(comments, []) == comments
    assert matches_comment("任意", []) is True
