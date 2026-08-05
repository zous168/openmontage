"""Tests for lib.error_digest."""

from plugins.openmontage.lib.error_digest import summarize_error_text


def test_dedupes_remotion_tab_lines():
    raw = "\n".join(
        f"[Tab {i}, node_modules/remotion/dist/esm/index.mjs:9805] "
        "Could not load image with source file:///H:/work/proj/assets/sc1.jpg"
        for i in range(5)
    )
    out = summarize_error_text(raw)
    assert out.count("Could not load image") == 1
    assert "重复 5 次" in out
    assert "file://" in out or "public-dir" in out.lower() or "提示" in out


def test_preserves_distinct_lines():
    raw = "line one\nline two\nline one"
    out = summarize_error_text(raw)
    assert "line one （重复 2 次）" in out
    assert "line two" in out


def test_empty_input():
    assert summarize_error_text("") == ""
    assert summarize_error_text("   ") == "   "
