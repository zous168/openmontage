"""将 pipeline_defs/*.yaml 各 stage 的 outputs 统一为 text/audio/video/image。

- text：每个 produces 产物一条，label=artifact 名，无 source → Flow 展示整份 JSON
- image/video/audio：按 STAGE_MEDIA 从产物内提取路径

规则见 scripts/OUTPUTS_SPEC.md
用法: python scripts/sync_pipeline_outputs.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 跳过 decision_log（审计日志，非阶段主产物展示）
SKIP_TEXT_ARTIFACTS = frozenset({"decision_log"})

# (kind, label, source) — source 为 artifacts 下的完整路径(artifact.field[].path)
STAGE_MEDIA: dict[str, list[tuple[str, str, str]]] = {
    "reference_analysis": [
        ("image", "参考帧", "video_analysis_brief.keyframes[].path"),
    ],
    "rig_plan": [
        ("image", "绑骨部件", "rig_plan.characters[].parts[].asset_path"),
    ],
    "assets": [
        ("image", "图片", "asset_manifest.assets[].path"),
        ("video", "视频", "asset_manifest.assets[].path"),
        ("audio", "音频", "asset_manifest.assets[].path"),
    ],
    "edit": [
        ("video", "片段", "edit_decisions.cuts[].source"),
    ],
    "compose": [
        ("video", "成片", "render_report.outputs[].path"),
    ],
    "publish": [
        ("video", "成片", "render_report.outputs[].path"),
        ("video", "导出", "publish_log.entries[].export_path"),
    ],
}

STAGE_RE = re.compile(r"^(\s*)- name:\s*(\S+)\s*$")
PRODUCE_ITEM_RE = re.compile(r"^\s*-\s+(\S+)\s*$")


def stage_spans(lines: list[str]) -> list[tuple[int, int, str, int]]:
    starts = [(i, m.group(2), len(m.group(1))) for i, m in
              ((i, STAGE_RE.match(l)) for i, l in enumerate(lines)) if m]
    out = []
    for idx, (start, name, indent) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        out.append((start, end, name, indent))
    return out


def find_key_block(lines: list[str], start: int, end: int, key: str, indent: int) -> tuple[int, int] | None:
    for i in range(start, end):
        line = lines[i]
        if line.strip() != f"{key}:":
            continue
        ind = len(line) - len(line.lstrip())
        if ind < indent:
            continue
        j = i + 1
        while j < end:
            lj = lines[j]
            if lj.strip() and len(lj) - len(lj.lstrip()) <= ind and not lj.strip().startswith("-"):
                break
            j += 1
        return i, j
    return None


def parse_produces(lines: list[str], start: int, end: int, indent: int) -> list[str]:
    pb = find_key_block(lines, start, end, "produces", indent)
    if not pb:
        return []
    names: list[str] = []
    for i in range(pb[0] + 1, pb[1]):
        m = PRODUCE_ITEM_RE.match(lines[i])
        if m:
            names.append(m.group(1))
    return names


def detect_list_indent(lines: list[str], block_start: int, block_end: int, key_indent: int) -> int:
    for i in range(block_start + 1, block_end):
        line = lines[i]
        if line.strip().startswith("- "):
            return len(line) - len(line.lstrip())
    return key_indent + 2


def build_outputs_lines(
    key_indent: int,
    item_indent: int,
    items: list[tuple[str, str, str | None]],
) -> list[str]:
    base = " " * key_indent
    out = [f"{base}outputs:"]
    for kind, label, source in items:
        out.append(f"{' ' * item_indent}- kind: {kind}")
        out.append(f"{' ' * (item_indent + 2)}label: {label}")
        if source:
            out.append(f"{' ' * (item_indent + 2)}source: {source}")
    return out


def outputs_for_stage(stage_name: str, produces: list[str]) -> list[tuple[str, str, str | None]]:
    items: list[tuple[str, str, str | None]] = []
    for art in produces:
        if art in SKIP_TEXT_ARTIFACTS:
            continue
        items.append(("text", art, None))
    for kind, label, source in STAGE_MEDIA.get(stage_name, []):
        items.append((kind, label, source))
    return items


def patch_file(path: Path, dry_run: bool) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    edits: list[tuple[int, int, list[str]]] = []
    for start, end, name, indent in stage_spans(lines):
        produces = parse_produces(lines, start, end, indent)
        if not produces:
            continue
        items = outputs_for_stage(name, produces)
        if not items:
            continue
        ob = find_key_block(lines, start, end, "outputs", indent)
        pb = find_key_block(lines, start, end, "produces", indent)
        if pb is None:
            continue
        p_indent = len(lines[pb[0]]) - len(lines[pb[0]].lstrip())
        item_indent = detect_list_indent(lines, pb[0], pb[1], p_indent)
        if ob:
            item_indent = detect_list_indent(lines, ob[0], ob[1], p_indent)
        new_block = build_outputs_lines(p_indent, item_indent, items)
        if ob:
            edits.append((ob[0], ob[1], new_block))
        else:
            edits.append((pb[1], pb[1], new_block))
    if not edits:
        return 0
    if dry_run:
        print(f"{path.name}: would replace {len(edits)} outputs block(s)")
        return len(edits)
    for s, e, new_block in sorted(edits, key=lambda x: x[0], reverse=True):
        lines[s:e] = new_block
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{path.name}: updated {len(edits)} stage(s)")
    return len(edits)


def main() -> None:
    dry = "--dry-run" in sys.argv
    total = 0
    for path in sorted((ROOT / "pipeline_defs").glob("*.yaml")):
        total += patch_file(path, dry)
    print(f"done: {total} stage output block(s)")


if __name__ == "__main__":
    main()
