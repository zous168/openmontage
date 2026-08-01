"""Pipeline manifest admin — read and update standardized pipeline_defs/ metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import jsonschema
import yaml

from backlot.bootstrap import BootstrapError, bootstrap_fields_for_pipeline, pipeline_ui_from_manifest
from backlot.dependency_catalog import tool_label_zh
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
_ARTIFACTS_SCHEMA_DIR = REPO_ROOT / "schemas" / "artifacts"

_STAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

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
    name = stage.get("name") or ""
    if name:
        return stage_label_zh(name)
    skill = stage.get("skill") or ""
    if skill:
        return stage_label_zh(skill.rsplit("/", 1)[-1])
    return stage_label_zh(name)


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
        "agent": stage.get("agent"),
        "preferred_tools": list(stage.get("preferred_tools") or []),
        "fallback_tools": list(stage.get("fallback_tools") or []),
        "required_tools": list(stage.get("required_tools") or []),
        "optional_tools": list(stage.get("optional_tools") or []),
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
    entry["manifest"] = manifest
    entry["default_checkpoint_policy"] = manifest.get("default_checkpoint_policy")
    entry["compatible_playbooks"] = manifest.get("compatible_playbooks")
    entry["orchestration"] = manifest.get("orchestration") or {}
    entry["reference_input"] = manifest.get("reference_input") or {}
    entry["extensions"] = manifest.get("extensions") or {}
    entry["metadata"] = manifest.get("metadata") or {}
    try:
        entry["editor_hints"] = build_pipeline_editor_hints(pipeline_id)
    except BootstrapError:
        entry["editor_hints"] = {"artifacts": _artifact_names(), "tools": _tool_names(), "tool_options": _tool_options(), "skills": []}
    return entry


def _clean_str_list(items: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for item in items or []:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _normalize_skill_ref(skill_ref: Optional[str]) -> Optional[str]:
    if skill_ref is None:
        return None
    ref = str(skill_ref).strip().replace("\\", "/").strip("/")
    if not ref:
        return None
    if ref.endswith(".md"):
        ref = ref[:-3]
    if ".." in ref.split("/"):
        raise BootstrapError("无效的技能路径。")
    return ref


def _validate_stage_name(name: str) -> str:
    text = (name or "").strip()
    if not text or not _STAGE_NAME_RE.match(text):
        raise BootstrapError("阶段 ID 须为小写 snake_case（如 script、scene_plan）。")
    return text


def _load_manifest_dict(pipeline_id: str) -> dict[str, Any]:
    path = _manifest_path(pipeline_id)
    if not path.is_file():
        raise BootstrapError(f"找不到流水线「{pipeline_id}」。")
    with open(path, encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)
    if not isinstance(manifest, dict):
        raise BootstrapError(f"流水线清单格式无效：{pipeline_id}")
    return manifest


def _artifact_names() -> list[str]:
    if not _ARTIFACTS_SCHEMA_DIR.is_dir():
        return []
    return sorted(
        p.stem
        for p in _ARTIFACTS_SCHEMA_DIR.glob("*.schema.json")
        if p.is_file()
    )


def _tool_names() -> list[str]:
    try:
        from tools.tool_registry import registry

        registry.ensure_discovered()
        return sorted({tool.name for tool in registry._tools.values()})
    except Exception:
        return []


def _tool_options() -> list[dict[str, str]]:
    return [{"value": name, "label_zh": tool_label_zh(name)} for name in _tool_names()]


def _infer_skill_dir(pipeline_id: str, manifest: dict[str, Any]) -> str:
    ui = pipeline_ui_from_manifest(pipeline_id, manifest)
    skill_dir = (ui.get("skill_dir") or "").strip()
    if skill_dir:
        return skill_dir
    for stage in manifest.get("stages") or []:
        skill = _normalize_skill_ref(stage.get("skill"))
        if skill and skill.startswith("pipelines/"):
            parts = skill.split("/")
            if len(parts) >= 3:
                return parts[1]
    for ref in manifest.get("required_skills") or []:
        text = str(ref or "").replace("\\", "/").strip("/")
        if text.startswith("pipelines/"):
            parts = text.split("/")
            if len(parts) >= 3:
                return parts[1]
    return pipeline_id


def _pipeline_skill_refs(pipeline_id: str, manifest: Optional[dict[str, Any]] = None) -> list[str]:
    manifest = manifest if manifest is not None else _load_manifest_dict(pipeline_id)
    skill_dir = _infer_skill_dir(pipeline_id, manifest)
    refs: set[str] = set()
    for stage in manifest.get("stages") or []:
        skill = _normalize_skill_ref(stage.get("skill"))
        if skill:
            refs.add(skill)
    skills_root = _SKILLS_ROOT / "pipelines" / skill_dir
    if skills_root.is_dir():
        for path in sorted(skills_root.glob("*.md")):
            refs.add(f"pipelines/{skill_dir}/{path.stem}")
    return sorted(refs)


def build_pipeline_editor_hints(pipeline_id: str) -> dict[str, Any]:
    """Autocomplete sources for the pipeline stage structure editor."""
    manifest = _load_manifest_dict(pipeline_id)
    return {
        "artifacts": _artifact_names(),
        "tools": _tool_names(),
        "tool_options": _tool_options(),
        "skills": _pipeline_skill_refs(pipeline_id, manifest),
    }


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
    new_name: Optional[str] = None,
    skill: Optional[str] = None,
    produces: Optional[list[str]] = None,
    tools_available: Optional[list[str]] = None,
    required_artifacts_in: Optional[list[str]] = None,
    optional_artifacts_in: Optional[list[str]] = None,
    checkpoint_required: Optional[bool] = None,
    review_focus: Optional[list[str]] = None,
    success_criteria: Optional[list[str]] = None,
    human_approval_default: Optional[bool] = None,
    sub_stages: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Update stage manifest fields including skill, artifacts, and tools."""
    manifest = _load_manifest_dict(pipeline_id)
    stage = _find_stage(manifest, stage_name)

    if new_name is not None:
        renamed = _validate_stage_name(new_name)
        if renamed != stage_name and any(s.get("name") == renamed for s in manifest.get("stages") or []):
            raise BootstrapError(f"阶段「{renamed}」已存在。")
        stage["name"] = renamed

    if skill is not None:
        normalized = _normalize_skill_ref(skill)
        if normalized:
            stage["skill"] = normalized
        elif "skill" in stage:
            del stage["skill"]

    if produces is not None:
        stage["produces"] = _clean_str_list(produces)
    if tools_available is not None:
        tools = _clean_str_list(tools_available)
        if tools:
            stage["tools_available"] = tools
        elif "tools_available" in stage:
            del stage["tools_available"]
        for legacy_key in ("required_tools", "optional_tools", "preferred_tools", "fallback_tools"):
            stage.pop(legacy_key, None)
    if required_artifacts_in is not None:
        items = _clean_str_list(required_artifacts_in)
        if items:
            stage["required_artifacts_in"] = items
        elif "required_artifacts_in" in stage:
            del stage["required_artifacts_in"]
    if optional_artifacts_in is not None:
        items = _clean_str_list(optional_artifacts_in)
        if items:
            stage["optional_artifacts_in"] = items
        elif "optional_artifacts_in" in stage:
            del stage["optional_artifacts_in"]
    if checkpoint_required is not None:
        stage["checkpoint_required"] = bool(checkpoint_required)
    if review_focus is not None:
        stage["review_focus"] = _clean_str_list(review_focus)
    if success_criteria is not None:
        stage["success_criteria"] = _clean_str_list(success_criteria)
    if human_approval_default is not None:
        stage["human_approval_default"] = bool(human_approval_default)
    if sub_stages is not None:
        cleaned: list[dict[str, Any]] = []
        for sub in sub_stages:
            if not isinstance(sub, dict) or not sub.get("name"):
                continue
            entry_sub: dict[str, Any] = {"name": str(sub["name"]).strip()}
            if sub.get("description"):
                entry_sub["description"] = str(sub["description"]).strip()
            if sub.get("condition"):
                entry_sub["condition"] = str(sub["condition"]).strip()
            if sub.get("human_approval_default"):
                entry_sub["human_approval_default"] = True
            tools = _clean_str_list(sub.get("tools_available"))
            if tools:
                entry_sub["tools_available"] = tools
            focus = _clean_str_list(sub.get("review_focus"))
            if focus:
                entry_sub["review_focus"] = focus
            cleaned.append(entry_sub)
        if cleaned:
            stage["sub_stages"] = cleaned
        elif "sub_stages" in stage:
            del stage["sub_stages"]

    _write_manifest(pipeline_id, manifest)
    return _stage_detail(_find_stage(manifest, stage["name"]))


def add_pipeline_stage(
    pipeline_id: str,
    *,
    name: str,
    skill: Optional[str] = None,
    produces: Optional[list[str]] = None,
    tools_available: Optional[list[str]] = None,
    required_artifacts_in: Optional[list[str]] = None,
    optional_artifacts_in: Optional[list[str]] = None,
    checkpoint_required: bool = True,
    human_approval_default: bool = False,
    review_focus: Optional[list[str]] = None,
    success_criteria: Optional[list[str]] = None,
    insert_after: Optional[str] = None,
) -> dict[str, Any]:
    """Append or insert a new stage into the pipeline manifest."""
    manifest = _load_manifest_dict(pipeline_id)
    stage_id = _validate_stage_name(name)
    stages: list[dict[str, Any]] = list(manifest.get("stages") or [])
    if any(s.get("name") == stage_id for s in stages):
        raise BootstrapError(f"阶段「{stage_id}」已存在。")

    stage: dict[str, Any] = {"name": stage_id, "checkpoint_required": bool(checkpoint_required)}
    normalized_skill = _normalize_skill_ref(skill)
    if normalized_skill:
        stage["skill"] = normalized_skill
    if produces:
        stage["produces"] = _clean_str_list(produces)
    if tools_available:
        stage["tools_available"] = _clean_str_list(tools_available)
    if required_artifacts_in:
        stage["required_artifacts_in"] = _clean_str_list(required_artifacts_in)
    if optional_artifacts_in:
        stage["optional_artifacts_in"] = _clean_str_list(optional_artifacts_in)
    if human_approval_default:
        stage["human_approval_default"] = True
    if review_focus:
        stage["review_focus"] = _clean_str_list(review_focus)
    if success_criteria:
        stage["success_criteria"] = _clean_str_list(success_criteria)

    if insert_after:
        idx = next((i for i, s in enumerate(stages) if s.get("name") == insert_after), -1)
        if idx < 0:
            raise BootstrapError(f"找不到参考阶段「{insert_after}」。")
        stages.insert(idx + 1, stage)
    else:
        stages.append(stage)
    manifest["stages"] = stages
    _write_manifest(pipeline_id, manifest)
    return _stage_detail(stage)


def delete_pipeline_stage(pipeline_id: str, stage_name: str) -> dict[str, Any]:
    """Remove a stage from the pipeline manifest."""
    manifest = _load_manifest_dict(pipeline_id)
    stages: list[dict[str, Any]] = list(manifest.get("stages") or [])
    if len(stages) <= 1:
        raise BootstrapError("流水线至少保留一个阶段。")
    next_stages = [s for s in stages if s.get("name") != stage_name]
    if len(next_stages) == len(stages):
        raise BootstrapError(f"找不到阶段「{stage_name}」。")
    manifest["stages"] = next_stages
    _write_manifest(pipeline_id, manifest)
    return {"deleted": stage_name, "stage_count": len(next_stages)}


def reorder_pipeline_stages(pipeline_id: str, stage_names: list[str]) -> dict[str, Any]:
    """Reorder stages to match *stage_names* exactly."""
    manifest = _load_manifest_dict(pipeline_id)
    stages: list[dict[str, Any]] = list(manifest.get("stages") or [])
    by_name = {s.get("name"): s for s in stages}
    ordered_names = _clean_str_list(stage_names)
    if len(ordered_names) != len(stages) or set(ordered_names) != set(by_name):
        raise BootstrapError("阶段顺序列表必须与现有阶段一一对应。")
    manifest["stages"] = [by_name[name] for name in ordered_names]
    _write_manifest(pipeline_id, manifest)
    return get_pipeline_config(pipeline_id)


_CHECKPOINT_POLICIES = {"guided", "manual_all", "auto_noncreative"}
_CATEGORIES = {
    "talking_head", "generated", "hybrid", "screen_recording", "animation", "cinematic", "custom",
}
_STABILITIES = {"production", "beta"}
_REF_DEPTHS = {"transcript_only", "standard", "deep"}


def update_pipeline_manifest(
    pipeline_id: str,
    *,
    version: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    stability: Optional[str] = None,
    default_checkpoint_policy: Optional[str] = None,
    required_skills: Optional[list[str]] = None,
    compatible_playbooks: Optional[Any] = None,
    reference_input: Optional[dict[str, Any]] = None,
    orchestration: Optional[dict[str, Any]] = None,
    extensions: Optional[dict[str, Any]] = None,
    ui: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Update top-level manifest fields (never rewrites ``stages``)."""
    manifest = _load_manifest_dict(pipeline_id)

    if version is not None:
        text = version.strip()
        if text:
            manifest["version"] = text
    if description is not None:
        manifest["description"] = description.strip()
    if category is not None:
        cat = category.strip()
        if cat not in _CATEGORIES:
            raise BootstrapError(f"无效 category：{cat}")
        manifest["category"] = cat
    if stability is not None:
        stab = stability.strip()
        if stab not in _STABILITIES:
            raise BootstrapError(f"无效 stability：{stab}")
        manifest["stability"] = stab
    if default_checkpoint_policy is not None:
        pol = default_checkpoint_policy.strip()
        if pol not in _CHECKPOINT_POLICIES:
            raise BootstrapError(f"无效 default_checkpoint_policy：{pol}")
        manifest["default_checkpoint_policy"] = pol
    if required_skills is not None:
        manifest["required_skills"] = _clean_str_list(required_skills)
    if compatible_playbooks is not None:
        manifest["compatible_playbooks"] = compatible_playbooks
    if reference_input is not None:
        ref = dict(reference_input)
        depth = str(ref.get("analysis_depth") or "standard")
        if depth not in _REF_DEPTHS:
            raise BootstrapError(f"无效 analysis_depth：{depth}")
        manifest["reference_input"] = {
            "supported": bool(ref.get("supported")),
            "analysis_depth": depth,
            "analysis_tools": _clean_str_list(ref.get("analysis_tools")),
        }
    if orchestration is not None:
        manifest["orchestration"] = orchestration
    if extensions is not None:
        manifest["extensions"] = {
            "custom_scripts": bool(extensions.get("custom_scripts", True)),
            "custom_playbooks": bool(extensions.get("custom_playbooks", True)),
            "custom_skills": bool(extensions.get("custom_skills", True)),
            "custom_tools": bool(extensions.get("custom_tools", False)),
        }
    if ui is not None:
        ui_block = dict(manifest.get("ui") or {})
        for key in ("label_zh", "summary_zh", "skill_dir"):
            if key in ui:
                text = str(ui[key] or "").strip()
                if text:
                    ui_block[key] = text
                elif key in ui_block:
                    del ui_block[key]
        if "hidden" in ui:
            if ui.get("hidden"):
                ui_block["hidden"] = True
            elif "hidden" in ui_block:
                del ui_block["hidden"]
        if ui_block:
            manifest["ui"] = ui_block
        elif "ui" in manifest:
            del manifest["ui"]
    if metadata is not None:
        if metadata:
            manifest["metadata"] = metadata
        elif "metadata" in manifest:
            del manifest["metadata"]

    _write_manifest(pipeline_id, manifest)
    return get_pipeline_config(pipeline_id)


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
