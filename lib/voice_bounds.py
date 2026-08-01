"""Listenability bounds for TTS — agents must not exceed normal speech rate.

When narration is too long for a section, extend the edit timeline or trim
copy — do NOT compress speech beyond these floors with length_scale / atempo.

See skills/meta/voice-performance-director.md → Listenability Floor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

# Piper: length_scale < 1.0 = faster. Floor 0.85 ≈ at most ~18% faster than normal.
PIPER_LENGTH_SCALE_FLOOR = 0.85
PIPER_LENGTH_SCALE_CEILING = 1.25

# FFmpeg atempo applied after synthesis — extra squeeze without user approval.
ATEMPO_LISTENABLE_MIN = 0.92
ATEMPO_LISTENABLE_MAX = 1.05

_LENGTH_SCALE_RE = re.compile(r"length_scale\s*=\s*([0-9.]+)", re.I)
_ATEMPO_RE = re.compile(r"atempo(?:\s*[=:]?\s*|\s+)([0-9.]+)", re.I)
_PROVIDER_LENGTH_SCALE_RE = re.compile(
    r"length_scale\s*=\s*([0-9.]+)", re.I
)


def parse_length_scale_from_text(text: str) -> Optional[float]:
    match = _LENGTH_SCALE_RE.search(text or "")
    return float(match.group(1)) if match else None


def parse_atempo_from_text(text: str) -> Optional[float]:
    match = _ATEMPO_RE.search(text or "")
    return float(match.group(1)) if match else None


def script_piper_length_scale(script: dict[str, Any]) -> Optional[float]:
    vp = script.get("voice_performance") or {}
    notes = vp.get("provider_notes") or {}
    piper_note = notes.get("piper") or ""
    return parse_length_scale_from_text(str(piper_note))


def check_narration_asset_listenability(
    asset: dict[str, Any],
    *,
    script_floor: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Return findings for one narration asset dict from asset_manifest."""
    findings: list[dict[str, Any]] = []
    if asset.get("type") != "narration":
        return findings

    summary = str(asset.get("generation_summary") or "")
    provider = str(asset.get("provider") or asset.get("source_tool") or "")
    length_scale = parse_length_scale_from_text(summary)
    atempo = parse_atempo_from_text(summary)

    effective_floor = PIPER_LENGTH_SCALE_FLOOR
    if script_floor is not None:
        # Never go faster (lower length_scale) than the script planned.
        effective_floor = max(effective_floor, script_floor)

    if length_scale is not None and "piper" in (provider + summary).lower():
        if length_scale < effective_floor:
            findings.append({
                "severity": "critical",
                "code": "voice_listenability_violation",
                "stage": "assets",
                "message": (
                    f"Narration asset {asset.get('id')!r} uses Piper length_scale="
                    f"{length_scale} (listenability floor {effective_floor}). "
                    f"Speech will sound unnaturally fast."
                ),
                "proposed_fix": (
                    "Re-generate TTS at script provider_notes length_scale or "
                    f">= {PIPER_LENGTH_SCALE_FLOOR}; extend edit timeline or trim "
                    "copy instead of speeding up."
                ),
            })
        elif length_scale > PIPER_LENGTH_SCALE_CEILING:
            findings.append({
                "severity": "suggestion",
                "code": "voice_listenability_slow",
                "stage": "assets",
                "message": (
                    f"Narration asset {asset.get('id')!r} uses Piper length_scale="
                    f"{length_scale} (above ceiling {PIPER_LENGTH_SCALE_CEILING})."
                ),
                "proposed_fix": "Use length_scale closer to 1.0 unless deliberate slow delivery.",
            })

    if atempo is not None:
        if atempo > ATEMPO_LISTENABLE_MAX or atempo < ATEMPO_LISTENABLE_MIN:
            findings.append({
                "severity": "critical",
                "code": "voice_listenability_violation",
                "stage": "assets",
                "message": (
                    f"Narration asset {asset.get('id')!r} applies atempo={atempo} "
                    f"outside listenable range "
                    f"[{ATEMPO_LISTENABLE_MIN}, {ATEMPO_LISTENABLE_MAX}] without "
                    f"documented user approval."
                ),
                "proposed_fix": (
                    "Remove post-TTS atempo squeeze; fit timeline by editing cuts or "
                    "script length. Log downgrade_approval if user explicitly accepts faster speech."
                ),
            })

    if "atempo fit" in summary.lower() and atempo is None:
        findings.append({
            "severity": "critical",
            "code": "voice_listenability_violation",
            "stage": "assets",
            "message": (
                f"Narration asset {asset.get('id')!r} records 'atempo fit' — "
                "post-TTS speed squeeze to match timeline is forbidden unless the "
                "user explicitly approved faster speech."
            ),
            "proposed_fix": (
                "Re-generate narration at natural pace; stretch scene_plan/edit "
                "durations to match audio."
            ),
        })

    return findings


def check_project_voice_listenability(project_dir: Path) -> list[dict[str, Any]]:
    """Scan asset_manifest (+ script) for listenability violations."""
    findings: list[dict[str, Any]] = []
    manifest_path = project_dir / "artifacts" / "asset_manifest.json"
    script_path = project_dir / "artifacts" / "script.json"

    if not manifest_path.is_file():
        return findings

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return findings

    script_floor: Optional[float] = None
    if script_path.is_file():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            script_floor = script_piper_length_scale(script)
        except (json.JSONDecodeError, OSError):
            script_floor = None

    for asset in manifest.get("assets") or []:
        findings.extend(
            check_narration_asset_listenability(asset, script_floor=script_floor)
        )

    return findings
