"""Compress repetitive tool/Remotion error logs for events.jsonl and UI."""

from __future__ import annotations

import re
from collections import Counter

# Strip Remotion parallel-tab prefix so identical root causes dedupe together.
_TAB_PREFIX = re.compile(r"^\[Tab \d+,[^\]]+\]\s*")


def _normalize_line(line: str) -> str:
    return _TAB_PREFIX.sub("", line.strip())


def summarize_error_text(text: str, *, max_lines: int = 24, max_chars: int = 8000) -> str:
    """Collapse repeated lines (e.g. Remotion Tab 0–4) and append actionable hints."""
    if not text or not str(text).strip():
        return text or ""

    raw = str(text).strip()
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return raw[:max_chars]

    counts: Counter[str] = Counter()
    order: list[str] = []
    for line in lines:
        key = _normalize_line(line)
        if key not in counts:
            order.append(key)
        counts[key] += 1

    out: list[str] = []
    for key in order[:max_lines]:
        n = counts[key]
        suffix = f" （重复 {n} 次）" if n > 1 else ""
        out.append(f"{key}{suffix}")

    omitted = len(order) - max_lines
    if omitted > 0:
        out.append(f"… 另有 {omitted} 条不同错误未显示")

    hint = _actionable_hint(raw)
    if hint and hint not in out:
        out.append("")
        out.append(hint)

    joined = "\n".join(out)
    if len(joined) > max_chars:
        joined = joined[: max_chars - 20].rstrip() + "\n…（错误过长已截断）"
    return joined


def _actionable_hint(text: str) -> str:
    lower = text.lower()
    if "not allowed to load local resource" in lower or "file:///" in lower:
        return (
            "提示：Remotion 浏览器无法加载 file:// 本地路径。"
            "应使用 --public-dir 指向项目目录，并在 props 中使用相对路径（如 assets/images/sc1.jpg）。"
        )
    if "could not load image" in lower and "file://" in lower:
        return (
            "提示：图片路径应相对于项目根目录，且合成时需设置 public-dir。"
        )
    if "缺少必填参数" in text:
        return "提示：检查工具 input_schema 的 required 字段是否都已传入。"
    return ""
