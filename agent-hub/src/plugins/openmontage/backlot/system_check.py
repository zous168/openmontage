"""System dependency audit for Backlot — tools, binaries, and runtime checks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from plugins.openmontage.backlot.dependency_catalog import (
    enrich_core_binary,
    lookup_dependency,
    tool_install_hint_zh,
    tool_label_zh,
)
from plugins.openmontage.tools.base_tool import ToolStatus
from plugins.openmontage.tools.tool_registry import registry

_CORE_BINARIES: tuple[tuple[str, list[str]], ...] = (
    ("ffmpeg", ["-version"]),
    ("ffprobe", ["-version"]),
    ("node", ["--version"]),
    ("npm", ["--version"]),
)

_CAPABILITY_PURPOSE: dict[str, str] = {
    "analysis": "内容分析",
    "audio_processing": "音频处理",
    "avatar": "数字人 / 口型",
    "character_animation": "角色动画",
    "clip_acquisition": "素材检索",
    "clip_retrieval": "片段检索",
    "corpus_population": "语料库构建",
    "enhancement": "画质增强",
    "image_generation": "图像生成",
    "music_generation": "音乐生成",
    "narration": "旁白 / TTS",
    "planning": "策划与编排",
    "publish": "发布导出",
    "source_media": "源素材",
    "subtitle": "字幕",
    "tts": "语音合成",
    "video_generation": "视频生成",
    "video_post": "视频后期",
    "visual_style": "视觉风格",
    "voice": "配音",
}


def _parse_dependency(dep: str) -> tuple[str, str]:
    if dep.startswith("binary:"):
        return "binary", dep[7:]
    if dep.startswith("cmd:"):
        return "cmd", dep[4:]
    if dep.startswith("env:"):
        return "env", dep[4:]
    if dep.startswith("python:"):
        return "python", dep[7:]
    return "unknown", dep


def _dependency_purpose(kind: str, tool) -> str:
    kind_label = {
        "binary": "系统可执行文件",
        "cmd": "命令行工具",
        "env": "API / 环境配置",
        "python": "Python 包",
    }.get(kind, "依赖项")
    cap_label = _CAPABILITY_PURPOSE.get(tool.capability, tool.capability)
    if tool.best_for:
        return f"{kind_label} · {tool.best_for[0]}"
    return f"{kind_label} · {cap_label}"


def _resolve_dependency_path(kind: str, name: str, *, probe: bool) -> tuple[Optional[str], Optional[bool]]:
    if kind in ("binary", "cmd"):
        if probe:
            path = shutil.which(name)
            return path, path is not None
        return "系统 PATH", None
    if kind == "env":
        if probe:
            return f"${name}", bool(os.environ.get(name))
        return f"${name}", None
    if kind == "python":
        if probe:
            try:
                mod = __import__(name)
                mod_path = getattr(mod, "__file__", None)
                return mod_path or f"pip:{name}", True
            except ImportError:
                return f"pip install {name}", False
        return f"pip:{name}", None
    return None, None


_KIND_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("cmd", "系统命令", "需在系统 PATH 中可用的可执行文件"),
    ("python", "Python 包", "通过 pip 安装的外部库"),
    ("env", "API 密钥", "在「环境变量」标签或 .env 中配置"),
)


def _normalize_exec_kind(kind: str) -> str:
    if kind in ("binary", "cmd"):
        return "cmd"
    return kind


def _aggregate_key(kind: str, name: str) -> str:
    return f"{_normalize_exec_kind(kind)}:{name}"



def aggregate_external_dependencies(*, probe: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate declared tool dependencies into installable external packages."""
    registry.ensure_discovered()
    by_key: dict[str, dict[str, Any]] = {}

    for tool in registry._tools.values():
        if tool.provider == "selector":
            continue
        for dep in tool.dependencies:
            kind, name = _parse_dependency(dep)
            norm_kind = _normalize_exec_kind(kind)
            key = _aggregate_key(kind, name)
            if key not in by_key:
                resolve_kind = "binary" if norm_kind == "cmd" else norm_kind
                path, ok = _resolve_dependency_path(resolve_kind, name, probe=probe)
                meta = lookup_dependency(norm_kind, name)
                by_key[key] = {
                    "id": dep,
                    "kind": norm_kind,
                    "name": name,
                    "label_zh": meta["label_zh"],
                    "description_zh": meta["description_zh"],
                    "tools": [],
                    "tools_zh": [],
                    "path": path,
                    "ok": ok,
                    "install_hint": meta["install_hint_zh"],
                }
            if tool.name not in by_key[key]["tools"]:
                by_key[key]["tools"].append(tool.name)
                by_key[key]["tools_zh"].append(tool_label_zh(tool.name))

    for entry in by_key.values():
        entry["purpose"] = entry["description_zh"]
        entry["tools"].sort()
        entry["tools_zh"] = [tool_label_zh(n) for n in entry["tools"]]

    groups: list[dict[str, Any]] = []
    for kind_id, label, description in _KIND_GROUPS:
        items = [v for v in by_key.values() if v["kind"] == kind_id]
        items.sort(key=lambda x: x["name"].lower())
        if items:
            groups.append({
                "id": kind_id,
                "label": label,
                "description": description,
                "items": items,
            })

    total = len(by_key)
    ok_count = sum(1 for v in by_key.values() if v.get("ok") is True)
    missing = sum(1 for v in by_key.values() if v.get("ok") is False)
    summary = {
        "deps_total": total,
        "deps_ok": ok_count if probe else None,
        "deps_missing": missing if probe else None,
    }
    return groups, summary


def enrich_tool_dependencies(tool, *, probe: bool) -> list[dict[str, Any]]:
    """Turn declared dependency strings into UI-friendly records with purpose and path."""
    items: list[dict[str, Any]] = []
    for dep in tool.dependencies:
        kind, name = _parse_dependency(dep)
        path, ok = _resolve_dependency_path(kind, name, probe=probe)
        items.append({
            "id": dep,
            "kind": kind,
            "name": name,
            "label_zh": lookup_dependency(kind, name)["label_zh"],
            "description_zh": _dependency_purpose(kind, tool),
            "purpose": _dependency_purpose(kind, tool),
            "path": path,
            "ok": ok,
        })
    return items


def _check_single_dependency(dep: str, install_hint: str = "") -> Optional[str]:
    """Return an error message when *dep* is unsatisfied, else ``None``."""
    hint = f" {install_hint}".rstrip()
    if dep.startswith(("cmd:", "binary:")):
        prefix = "cmd:" if dep.startswith("cmd:") else "binary:"
        cmd_name = dep[len(prefix):]
        if shutil.which(cmd_name) is None:
            return f"找不到命令 {cmd_name!r}.{hint}"
        return None
    if dep.startswith("env:"):
        env_name = dep[4:]
        if not os.environ.get(env_name):
            return f"环境变量 {env_name!r} 未设置.{hint}"
        return None
    if dep.startswith("python:"):
        module_name = dep[7:]
        try:
            __import__(module_name)
        except ImportError:
            return f"Python 模块 {module_name!r} 未安装.{hint}"
        return None
    return None


def quick_tool_status(tool) -> tuple[str, list[dict[str, str]]]:
    """Fast dependency-only status — no network or ComfyUI probes."""
    issues: list[dict[str, str]] = []
    for dep in tool.dependencies:
        msg = _check_single_dependency(dep, tool.install_instructions)
        if msg:
            issues.append({"dependency": dep, "message": msg})
    status = ToolStatus.AVAILABLE.value if not issues else ToolStatus.UNAVAILABLE.value
    return status, issues


def _probe_binary(name: str, args: list[str]) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {"name": name, "ok": False, "path": None, "detail": "未找到可执行文件"}
    try:
        result = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        text = (result.stdout or result.stderr or "").strip()
        detail = text.splitlines()[0] if text else "已安装"
        return {"name": name, "ok": result.returncode == 0, "path": path, "detail": detail}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"name": name, "ok": False, "path": path, "detail": str(exc)}


def _composition_runtimes_fast() -> dict[str, bool]:
    registry.ensure_discovered()
    vc = registry._tools.get("video_compose")
    if vc is None:
        return {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "remotion": bool(shutil.which("npx") or shutil.which("node")),
            "hyperframes": bool(shutil.which("npx") or shutil.which("node")),
        }
    return {
        "ffmpeg": vc._ffmpeg_available(),
        "remotion": vc._remotion_available(),
        "hyperframes": vc._hyperframes_available(),
    }


def _build_provider_menu(*, deep: bool) -> dict[str, dict[str, Any]]:
    """Build capability-grouped tool menu.

    *deep=False* uses dependency-only checks (fast, for UI checklist).
    *deep=True* uses each tool's ``get_status()`` (may probe ComfyUI etc.).
    """
    registry.ensure_discovered()
    menu: dict[str, dict[str, Any]] = {}

    for tool in registry._tools.values():
        if tool.provider == "selector":
            continue
        cap = tool.capability
        if cap not in menu:
            menu[cap] = {"available": [], "unavailable": [], "total": 0, "configured": 0}

        if deep:
            status = tool.get_status()
            issues: list[dict[str, str]] = []
            if status != ToolStatus.AVAILABLE:
                for dep in tool.dependencies:
                    msg = _check_single_dependency(dep, tool.install_instructions)
                    if msg:
                        issues.append({"dependency": dep, "message": msg})
        else:
            status_value, issues = quick_tool_status(tool)
            status = ToolStatus(status_value)

        entry: dict[str, Any] = {
            "name": tool.name,
            "provider": tool.provider,
            "runtime": tool.runtime.value,
            "best_for": tool.best_for,
            "dependencies": list(tool.dependencies),
            "install_instructions": tool.install_instructions,
            "status": status.value,
        }
        if issues:
            entry["issues"] = issues

        if not deep:
            env_vars = [dep[4:] for dep in tool.dependencies if dep.startswith("env:")]
            if env_vars and status != ToolStatus.AVAILABLE:
                entry["setup_offer"] = {"env_vars": env_vars}

        if status == ToolStatus.AVAILABLE:
            menu[cap]["available"].append(entry)
            menu[cap]["configured"] += 1
        else:
            menu[cap]["unavailable"].append(entry)
        menu[cap]["total"] += 1

    for bucket in menu.values():
        bucket["available"].sort(key=lambda entry: (entry["provider"], entry["name"]))
        bucket["unavailable"].sort(key=lambda entry: (entry["provider"], entry["name"]))

    return dict(sorted(menu.items()))


def _capabilities_from_menu(menu: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    for cap, bucket in menu.items():
        available_providers = {e.get("provider") for e in bucket.get("available", [])} - {None}
        unavailable_providers = (
            {e.get("provider") for e in bucket.get("unavailable", [])}
            - {None}
            - available_providers
        )
        capabilities.append({
            "capability": cap,
            "configured": bucket.get("configured", 0),
            "total": bucket.get("total", 0),
            "available_providers": sorted(available_providers),
            "unavailable_providers": sorted(unavailable_providers),
        })
    return capabilities


def _setup_offers_from_menu(menu: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    for cap, bucket in menu.items():
        for entry in bucket.get("unavailable", []):
            tool_name = entry.get("name") or ""
            install_instructions = entry.get("install_instructions") or ""
            env_vars = [
                dep[4:]
                for dep in entry.get("dependencies", [])
                if isinstance(dep, str) and dep.startswith("env:")
            ]
            offer = entry.get("setup_offer")
            if offer:
                env_vars = list(offer.get("env_vars") or env_vars)
            if not offer and not env_vars:
                continue
            row: dict[str, Any] = {
                "capability": cap,
                "tool": tool_name,
                "tool_label_zh": tool_label_zh(tool_name),
                "provider": entry.get("provider"),
                "install_instructions": install_instructions,
                "env_vars": env_vars,
            }
            if offer:
                row.update(offer)
                row["env_vars"] = list(offer.get("env_vars") or env_vars)
            row["install_hint_zh"] = tool_install_hint_zh(
                tool_name, install_instructions, env_vars=row.get("env_vars") or None,
            )
            offers.append(row)
    return offers


def _tool_checklist(menu: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    registry.ensure_discovered()
    tools_by_name = {t.name: t for t in registry._tools.values()}
    rows: list[dict[str, Any]] = []
    for cap, bucket in menu.items():
        for pool in ("available", "unavailable"):
            for entry in bucket.get(pool, []):
                tool = tools_by_name.get(entry["name"])
                rows.append({
                    "capability": cap,
                    "name": entry["name"],
                    "provider": entry.get("provider") or "",
                    "runtime": entry.get("runtime") or "",
                    "status": entry.get("status") or "unknown",
                    "dependencies": enrich_tool_dependencies(tool, probe=True) if tool else [],
                    "install_instructions": entry.get("install_instructions") or "",
                    "issues": entry.get("issues") or [],
                })
    rows.sort(key=lambda r: (r["capability"], r["provider"], r["name"]))
    return rows


def _tool_entries(*, verify: bool) -> list[dict[str, Any]]:
    registry.ensure_discovered()
    entries: list[dict[str, Any]] = []
    for tool in registry._tools.values():
        if tool.provider == "selector":
            continue
        if verify:
            status = tool.get_status()
            issues: list[dict[str, str]] = []
            if status != ToolStatus.AVAILABLE:
                for dep in tool.dependencies:
                    msg = _check_single_dependency(dep, tool.install_instructions)
                    if msg:
                        issues.append({"dependency": dep, "message": msg})
            status_value = status.value
        else:
            status_value, issues = quick_tool_status(tool)

        entry = {
            "name": tool.name,
            "label_zh": tool_label_zh(tool.name),
            "capability": tool.capability,
            "provider": tool.provider,
            "runtime": tool.runtime.value,
            "status": status_value,
            "dependencies": list(tool.dependencies),
            "install_instructions": tool.install_instructions or "",
        }
        if issues:
            entry["issues"] = issues
        entries.append(entry)
    entries.sort(key=lambda e: (e["capability"], e["provider"], e["name"]))
    return entries


def _core_binaries_manifest(*, probe: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, args in _CORE_BINARIES:
        meta = enrich_core_binary(name, "核心运行时")
        if probe:
            row = _probe_binary(name, args)
            row["label_zh"] = meta["label_zh"]
            row["purpose"] = meta["purpose"]
        else:
            row = {
                "name": name,
                "label_zh": meta["label_zh"],
                "ok": None,
                "path": None,
                "detail": "—",
                "purpose": meta["purpose"],
            }
        rows.append(row)
    py_meta = enrich_core_binary("python", "OpenMontage 主运行时")
    rows.append({
        "name": "python",
        "label_zh": py_meta["label_zh"],
        "ok": True if probe else None,
        "path": sys.executable,
        "detail": sys.version.splitlines()[0],
        "purpose": py_meta["purpose"],
    })
    return rows


def build_dependency_manifest() -> dict[str, Any]:
    """Static dependency manifest — no probing, for the default UI checklist."""
    dependency_groups, dep_summary = aggregate_external_dependencies(probe=False)

    binaries = _core_binaries_manifest(probe=False)

    return {
        "checked_at": None,
        "verified": False,
        "status_mode": "manifest",
        "summary": {
            **dep_summary,
            "setup_offers": 0,
            "runtime_warnings": 0,
            "binaries_ok": None,
            "binaries_total": len(binaries),
        },
        "composition_runtimes": {
            "ffmpeg": None,
            "remotion": None,
            "hyperframes": None,
        },
        "capabilities": [],
        "setup_offers": [],
        "runtime_warnings": [],
        "binaries": binaries,
        "dependency_groups": dependency_groups,
        "tool_checklist": [],
        "tools": [],
        "provider_menu": {},
    }


def run_system_check(*, verify: bool = False) -> dict[str, Any]:
    """Build a dependency report for the Backlot UI and agents."""
    deep = verify
    menu = _build_provider_menu(deep=deep)
    capabilities = _capabilities_from_menu(menu)
    setup_offers = _setup_offers_from_menu(menu)
    checklist = _tool_checklist(menu)
    dependency_groups, dep_summary = aggregate_external_dependencies(probe=True)

    binaries = _core_binaries_manifest(probe=True)

    runtime_warnings: list[str] = []
    if verify:
        hf = registry._tools.get("hyperframes_compose")
        if hf is not None:
            try:
                rc = hf.get_info().get("hyperframes_runtime") or {}
                for reason in rc.get("reasons") or []:
                    runtime_warnings.append(f"hyperframes: {reason}")
            except Exception as exc:
                runtime_warnings.append(f"hyperframes: {exc}")

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "verified": True,
        "status_mode": "operational" if verify else "dependencies",
        "summary": {
            **dep_summary,
            "setup_offers": len(setup_offers),
            "runtime_warnings": len(runtime_warnings),
            "binaries_ok": sum(1 for b in binaries if b.get("ok")),
            "binaries_total": len(binaries),
        },
        "composition_runtimes": _composition_runtimes_fast(),
        "capabilities": capabilities,
        "setup_offers": setup_offers,
        "runtime_warnings": runtime_warnings,
        "binaries": binaries,
        "dependency_groups": dependency_groups,
        "tool_checklist": checklist,
        "tools": _tool_entries(verify=verify) if verify else [],
        "provider_menu": menu,
    }
