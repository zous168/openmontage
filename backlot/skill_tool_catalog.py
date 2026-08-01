"""Skill and tool catalog for Backlot — grouped by business / knowledge layers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backlot.skill_catalog import enrich_skill_item
from backlot.bootstrap import list_pipeline_catalog

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_ROOT = _REPO_ROOT / "skills"
_LAYER3_ROOT = _REPO_ROOT / ".agents" / "skills"

_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")


def _read_title(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = _TITLE_RE.match(line.strip())
                if match:
                    return match.group(1).strip()
    except OSError:
        pass
    stem = path.stem.replace("-", " ").replace("_", " ")
    return stem.title()


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _humanize_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _pipeline_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    try:
        for entry in list_pipeline_catalog(include_hidden=True):
            pid = entry.get("id") or entry.get("pipeline_type") or ""
            if pid:
                labels[pid] = entry.get("label_zh") or _humanize_slug(pid)
    except OSError:
        pass
    return labels


def _scan_layer2_skills() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    if not _SKILLS_ROOT.is_dir():
        return groups

    pipeline_labels = _pipeline_labels()
    pipeline_skills: dict[str, list[dict[str, Any]]] = {}

    def skill_item(path: Path, *, category: str, pipeline: Optional[str] = None) -> dict[str, Any]:
        rel = _rel(path)
        stem = path.stem
        item: dict[str, Any] = {
            "kind": "skill",
            "layer": 2,
            "id": rel.removesuffix(".md"),
            "name": _read_title(path),
            "path": rel,
            "category": category,
        }
        if pipeline:
            item["pipeline"] = pipeline_labels.get(pipeline, _humanize_slug(pipeline))
            item["pipeline_id"] = pipeline
            item["stage"] = stem
        return enrich_skill_item(item)

    core_items = [
        skill_item(p, category="core")
        for p in sorted(_SKILLS_ROOT.joinpath("core").glob("*.md"))
    ]
    if core_items:
        groups.append({"id": "core", "label_key": "catalogGroupCore", "items": core_items})

    creative_root = _SKILLS_ROOT / "creative"
    creative_items: list[dict[str, Any]] = []
    if creative_root.is_dir():
        for path in sorted(creative_root.rglob("*.md")):
            if path.is_file():
                sub = path.parent.relative_to(creative_root)
                subcat = sub.as_posix() if sub.parts else ""
                item = skill_item(path, category="creative")
                if subcat:
                    item["subcategory"] = subcat
                creative_items.append(item)
    if creative_items:
        groups.append({"id": "creative", "label_key": "catalogGroupCreative", "items": creative_items})

    meta_items = [
        skill_item(p, category="meta")
        for p in sorted(_SKILLS_ROOT.joinpath("meta").glob("*.md"))
    ]
    if meta_items:
        groups.append({"id": "meta", "label_key": "catalogGroupMeta", "items": meta_items})

    pipelines_root = _SKILLS_ROOT / "pipelines"
    if pipelines_root.is_dir():
        for pipeline_dir in sorted(pipelines_root.iterdir()):
            if not pipeline_dir.is_dir():
                continue
            pid = pipeline_dir.name
            items = [
                skill_item(p, category="pipelines", pipeline=pid)
                for p in sorted(pipeline_dir.glob("*.md"))
            ]
            if items:
                pipeline_skills[pid] = items

    if pipeline_skills:
        subgroups = []
        for pid in sorted(pipeline_skills):
            subgroups.append({
                "id": pid,
                "label": pipeline_labels.get(pid, _humanize_slug(pid)),
                "items": pipeline_skills[pid],
            })
        groups.append({
            "id": "pipelines",
            "label_key": "catalogGroupPipelines",
            "subgroups": subgroups,
            "item_count": sum(len(g["items"]) for g in subgroups),
        })

    return groups


def _scan_layer3_skills() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not _LAYER3_ROOT.is_dir():
        return items
    for skill_dir in sorted(_LAYER3_ROOT.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        rel = _rel(skill_md)
        items.append(enrich_skill_item({
            "kind": "skill",
            "layer": 3,
            "id": skill_dir.name,
            "name": _read_title(skill_md),
            "path": rel,
            "category": "agent_skills",
        }))
    return items


def _count_layer2_items(groups: list[dict[str, Any]]) -> int:
    total = 0
    for group in groups:
        if group.get("subgroups"):
            total += sum(len(sg.get("items") or []) for sg in group["subgroups"])
        else:
            total += len(group.get("items") or [])
    return total


def build_skill_tool_catalog() -> dict[str, Any]:
    """Return Layer 2/3 skill catalog. Tool/env listing lives in system dependencies."""
    layer2_groups = _scan_layer2_skills()
    layer3_items = _scan_layer3_skills()

    layer2_total = _count_layer2_items(layer2_groups)
    pipeline_ids = {
        sg["id"]
        for g in layer2_groups
        if g.get("subgroups")
        for sg in g["subgroups"]
    }

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "layer2_skills": layer2_total,
            "layer3_skills": len(layer3_items),
            "pipelines_with_skills": len(pipeline_ids),
        },
        "layers": [
            {
                "id": "skills_l2",
                "layer": 2,
                "label_key": "catalogLayerSkillsL2",
                "description_key": "catalogLayerSkillsL2Desc",
                "groups": layer2_groups,
            },
            {
                "id": "skills_l3",
                "layer": 3,
                "label_key": "catalogLayerSkillsL3",
                "description_key": "catalogLayerSkillsL3Desc",
                "groups": [{
                    "id": "agent_skills",
                    "label_key": "catalogGroupAgentSkills",
                    "items": layer3_items,
                }],
            },
        ],
        "index_path": "skills/INDEX.md",
        "tools_tab": "deps",
    }
