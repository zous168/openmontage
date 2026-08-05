"""Tests for lib.voice_bounds listenability checks."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.openmontage.lib.production_audit import audit_project
from plugins.openmontage.lib.voice_bounds import (
    check_narration_asset_listenability,
    check_project_voice_listenability,
    script_piper_length_scale,
)


def test_script_piper_length_scale_parsed():
    script = {"voice_performance": {"provider_notes": {"piper": "zh, length_scale=0.95"}}}
    assert script_piper_length_scale(script) == 0.95


def test_length_scale_066_is_critical():
    findings = check_narration_asset_listenability({
        "id": "narr_full",
        "type": "narration",
        "provider": "piper_tts",
        "generation_summary": "Piper length_scale=0.66 + atempo fit",
    }, script_floor=0.95)
    codes = {f["code"] for f in findings}
    assert "voice_listenability_violation" in codes
    assert len(findings) >= 2


def test_length_scale_095_passes_with_script_floor():
    findings = check_narration_asset_listenability({
        "id": "narr_s1",
        "type": "narration",
        "provider": "piper_tts",
        "generation_summary": "Piper length_scale=0.95",
    }, script_floor=0.95)
    assert findings == []


def test_my_copy_01_manifest_would_fail_audit(tmp_path):
    project = tmp_path / "my-copy-01"
    (project / "artifacts").mkdir(parents=True)
    src = Path("h:/work/OpenMontage/projects/my-copy-01/artifacts")
    if not (src / "asset_manifest.json").exists():
        return  # skip if project not present in env
    (project / "artifacts" / "asset_manifest.json").write_text(
        (src / "asset_manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (project / "artifacts" / "script.json").write_text(
        (src / "script.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    findings = check_project_voice_listenability(project)
    assert any(f["code"] == "voice_listenability_violation" for f in findings)


def test_audit_project_includes_voice_check(tmp_path):
    project = tmp_path / "p1"
    (project / "artifacts").mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "reference-driven"}),
        encoding="utf-8",
    )
    (project / "artifacts" / "asset_manifest.json").write_text(json.dumps({
        "version": "1.0",
        "assets": [{
            "id": "n1",
            "type": "narration",
            "provider": "piper_tts",
            "generation_summary": "length_scale=0.66 + atempo fit",
        }],
    }), encoding="utf-8")
    findings = audit_project(project, pipeline_type="reference-driven")
    assert any(f["code"] == "voice_listenability_violation" for f in findings)
