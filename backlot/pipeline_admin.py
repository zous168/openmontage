"""Pipeline manifest admin — read and update standardized pipeline_defs/ metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import jsonschema
import yaml

from backlot.bootstrap import BootstrapError, bootstrap_fields_for_pipeline, pipeline_ui_from_manifest
from backlot.skill_catalog import stage_label_zh
from lib.paths import REPO_ROOT
from lib.pipeline_loader import (
    PIPELINE_DEFS_DIR,
    _load_manifest_schema,
    clear_pipeline_cache,
    list_pipelines,
    load_pipeline,
)

_SKILLS_ROOT = REPO_ROOT / "skills"

_CATEGORY_ZH: dict[str, str] = {
    "talking_head": "真人口播",
    "generated": "AI 生成",
    "hybrid": "混合制作",
    "screen_recording": "屏幕录制",
    "animation": "动画 / 动效",
    "cinematic": "电影感",
    "custom": "自定义",
}

_STABILITY_ZH: dict[str, str] = {
    "production": "生产",
    "beta": "测试",
}


def _manifest_path(pipeline_id: str) -> Path:
    pid = (pipeline_id or "").strip()
    if not pid or "/" in pid or "\\" in pid or ".." in pid:
        raise BootstrapError("无效的流水线 ID。")
    return PIPELINE_DEFS_DIR / f"{pid}.yaml"


def _skill_exists(skill_ref: Optional[str]) -> bool:
    if not skill_ref:
        return False
    return (_SKILLS_ROOT / f"{skill_ref}.md").is_file()


def _stage_label(stage: dict[str, Any]) -> str:
    skill = stage.get("skill") or ""
    if skill:
        return stage_label_zh(skill.rsplit("/", 1)[-1])
    return stage_label_zh(stage.get("name"))


def _stage_row(stage: dict[str, Any]) -> dict[str, Any]:
    name = stage.get("name") or ""
    skill = stage.get("skill")
    produces = list(stage.get("produces") or [])
    tools = list(stage.get("tools_available") or [])
    if not tools:
        tools = sorted(set(stage.get("required_tools") or []) | set(stage.get("optional_tools") or []))
    return {
        "name": name,
        "label_zh": _stage_label(stage),
        "skill": skill,
        "skill_ok": _skill_exists(skill),
        "produces": produces,
        "tools_available": tools,
        "human_approval_default": bool(stage.get("human_approval_default", False)),
        "checkpoint_required": stage.get("checkpoint_required", True),
        "sub_stages": [
            {
                "name": sub.get("name"),
                "description": sub.get("description"),
                "condition": sub.get("condition"),
            }
            for sub in (stage.get("sub_stages") or [])
        ],
    }


def _read_manifest_raw(pipeline_id: str) -> dict[str, Any]:
    path = PIPELINE_DEFS_DIR / f"{pipeline_id}.yaml"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def _load_manifest_resilient(pipeline_id: str) -> tuple[dict[str, Any], list[str]]:
    """Load manifest for admin display; fall back to raw YAML when schema validation fails."""
    issues: list[str] = []
    try:
        return load_pipeline(pipeline_id), issues
    except Exception as exc:
        manifest = _read_manifest_raw(pipeline_id)
        if not manifest:
            raise BootstrapError(f"无法读取流水线「{pipeline_id}」。") from exc
        issues.append(f"schema: {exc}")
        return manifest, issues


def _pipeline_admin_entry(pipeline_id: str) -> dict[str, Any]:
    manifest, manifest_issues = _load_manifest_resilient(pipeline_id)
    ui = pipeline_ui_from_manifest(pipeline_id, manifest)
    desc = manifest.get("description") or ""
    if isinstance(desc, str):
        desc = " ".join(desc.split())
    stages = [_stage_row(s) for s in manifest.get("stages") or []]
    missing_skills = sum(1 for s in stages if s.get("skill") and not s.get("skill_ok"))
    orch = manifest.get("orchestration") or {}
    return {
        "id": pipeline_id,
        "manifest_path": f"pipeline_defs/{pipeline_id}.yaml",
        "name": manifest.get("name") or pipeline_id,
        "version": manifest.get("version") or "",
        "label_zh": ui["label_zh"],
        "summary_zh": ui["summary_zh"],
        "hidden": ui["hidden"],
        "skill_dir": ui["skill_dir"],
        "description": desc[:400],
        "category": manifest.get("category") or "unknown",
        "category_zh": _CATEGORY_ZH.get(manifest.get("category") or "", manifest.get("category") or "—"),
        "stability": manifest.get("stability") or "unknown",
        "stability_zh": _STABILITY_ZH.get(manifest.get("stability") or "", manifest.get("stability") or "—"),
        "stage_count": len(stages),
        "stages": stages,
        "required_skills": list(manifest.get("required_skills") or []),
        "orchestration_mode": orch.get("mode"),
        "budget_default_usd": orch.get("budget_default_usd"),
        "bootstrap_field_count": len(bootstrap_fields_for_pipeline(pipeline_id)),
        "issues": {
            "missing_skill_files": missing_skills,
            "manifest": manifest_issues,
        },
    }


def build_pipeline_admin_catalog(*, include_hidden: bool = True) -> dict[str, Any]:
    """Full pipeline registry for Backlot admin UI."""
    entries = [_pipeline_admin_entry(name) for name in sorted(list_pipelines(PIPELINE_DEFS_DIR))]
    if not include_hidden:
        entries = [e for e in entries if not e.get("hidden")]
    visible = sum(1 for e in entries if not e.get("hidden"))
    production = sum(1 for e in entries if e.get("stability") == "production")
    issues = sum(e.get("issues", {}).get("missing_skill_files", 0) for e in entries)
    schema_issues = sum(1 for e in entries if e.get("issues", {}).get("manifest"))
    return {
        "summary": {
            "total": len(entries),
            "visible": visible,
            "hidden": len(entries) - visible,
            "production": production,
            "skill_issues": issues,
            "schema_issues": schema_issues,
        },
        "pipelines": entries,
    }


def _stage_detail(stage: dict[str, Any]) -> dict[str, Any]:
    """Full stage payload for the pipeline config editor."""
    row = _stage_row(stage)
    row.update({
        "required_artifacts_in": list(stage.get("required_artifacts_in") or []),
        "optional_artifacts_in": list(stage.get("optional_artifacts_in") or []),
        "review_focus": list(stage.get("review_focus") or []),
        "success_criteria": list(stage.get("success_criteria") or []),
        "sub_stages": [
            {
                "name": sub.get("name"),
                "description": sub.get("description"),
                "condition": sub.get("condition"),
                "human_approval_default": bool(sub.get("human_approval_default", False)),
                "tools_available": list(sub.get("tools_available") or []),
                "review_focus": list(sub.get("review_focus") or []),
            }
            for sub in (stage.get("sub_stages") or [])
        ],
    })
    return row


def _resolve_skill_path(skill_ref: str) -> Path:
    ref = (skill_ref or "").strip().replace("\\", "/").strip("/")
    if not ref or ".." in ref.split("/"):
        raise BootstrapError("无效的技能路径。")
    if not ref.endswith(".md"):
        ref_path = _SKILLS_ROOT / f"{ref}.md"
    else:
        ref_path = _SKILLS_ROOT / ref
    resolved = ref_path.resolve()
    root = _SKILLS_ROOT.resolve()
    if not str(resolved).startswith(str(root)):
        raise BootstrapError("技能路径越界。")
    return resolved


def read_skill_markdown(skill_ref: str) -> dict[str, Any]:
    path = _resolve_skill_path(skill_ref)
    if not path.is_file():
        raise BootstrapError(f"找不到技能文件：{skill_ref}")
    content = path.read_text(encoding="utf-8")
    rel = path.relative_to(_SKILLS_ROOT).as_posix()
    return {
        "path": rel.replace(".md", ""),
        "file_path": f"skills/{rel}",
        "content": content,
        "size": len(content),
    }


def write_skill_markdown(skill_ref: str, content: str) -> dict[str, Any]:
    path = _resolve_skill_path(skill_ref)
    if not path.is_file():
        raise BootstrapError(f"找不到技能文件：{skill_ref}")
    text = content if content is not None else ""
    path.write_text(text, encoding="utf-8", newline="\n")
    return read_skill_markdown(skill_ref)


def get_pipeline_config(pipeline_id: str) -> dict[str, Any]:
    """Full pipeline definition for the dedicated config page."""
    entry = _pipeline_admin_entry(pipeline_id)
    manifest, _ = _load_manifest_resilient(pipeline_id)
    stages = [_stage_detail(s) for s in manifest.get("stages") or []]
    entry["stages"] = stages
    entry["default_checkpoint_policy"] = manifest.get("default_checkpoint_policy")
    entry["compatible_playbooks"] = manifest.get("compatible_playbooks")
    entry["orchestration"] = manifest.get("orchestration") or {}
    return entry


def _find_stage(manifest: dict[str, Any], stage_name: str) -> dict[str, Any]:
    for stage in manifest.get("stages") or []:
        if stage.get("name") == stage_name:
            return stage
    raise BootstrapError(f"找不到阶段「{stage_name}」。")


def _write_manifest(pipeline_id: str, manifest: dict[str, Any]) -> None:
    jsonschema.validate(instance=manifest, schema=_load_manifest_schema())
    path = _manifest_path(pipeline_id)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(manifest, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    clear_pipeline_cache()


def update_pipeline_stage(
    pipeline_id: str,
    stage_name: str,
    *,
    review_focus: Optional[list[str]] = None,
    success_criteria: Optional[list[str]] = None,
    human_approval_default: Optional[bool] = None,
) -> dict[str, Any]:
    """Update per-stage manifest checklist fields (not stage name or skill path)."""
    path = _manifest_path(pipeline_id)
    if not path.is_file():
        raise BootstrapError(f"找不到流水线「{pipeline_id}」。")
    with open(path, encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    if not isinstance(manifest, dict):
        raise BootstrapError(f"流水线清单格式无效：{pipeline_id}")

    stage = _find_stage(manifest, stage_name)
    if review_focus is not None:
        stage["review_focus"] = [s.strip() for s in review_focus if s and s.strip()]
    if success_criteria is not None:
        stage["success_criteria"] = [s.strip() for s in success_criteria if s and s.strip()]
    if human_approval_default is not None:
        stage["human_approval_default"] = bool(human_approval_default)

    _write_manifest(pipeline_id, manifest)
    return _stage_detail(_find_stage(manifest, stage_name))


def update_pipeline_ui(
    pipeline_id: str,
    *,
    hidden: Optional[bool] = None,
    label_zh: Optional[str] = None,
    summary_zh: Optional[str] = None,
) -> dict[str, Any]:
    """Persist UI metadata into the manifest ``ui`` block (does not touch stages/skills)."""
    path = _manifest_path(pipeline_id)
    if not path.is_file():
        raise BootstrapError(f"找不到流水线「{pipeline_id}」。")

    with open(path, encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    if not isinstance(manifest, dict):
        raise BootstrapError(f"流水线清单格式无效：{pipeline_id}")

    ui = dict(manifest.get("ui") or {})
    if hidden is not None:
        ui["hidden"] = bool(hidden)
    if label_zh is not None:
        text = label_zh.strip()
        if text:
            ui["label_zh"] = text
        elif "label_zh" in ui:
            del ui["label_zh"]
    if summary_zh is not None:
        text = summary_zh.strip()
        if text:
            ui["summary_zh"] = text
        elif "summary_zh" in ui:
            del ui["summary_zh"]

    if ui:
        manifest["ui"] = ui
    elif "ui" in manifest:
        del manifest["ui"]

    jsonschema.validate(instance=manifest, schema=_load_manifest_schema())

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(manifest, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    clear_pipeline_cache()
    return _pipeline_admin_entry(pipeline_id)
