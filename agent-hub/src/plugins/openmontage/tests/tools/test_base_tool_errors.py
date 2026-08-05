"""Tests for tool error formatting and required-input validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.openmontage.tools.analysis.transcriber import Transcriber
from plugins.openmontage.tools.base_tool import ToolResult, format_tool_error, validate_required_inputs
from plugins.openmontage.tools.subtitle.subtitle_gen import SubtitleGen


def test_format_tool_error_keyerror():
    err = format_tool_error(KeyError("input_path"), tool_name="transcriber")
    assert "input_path" in err
    assert "缺少必填参数" in err
    assert "transcriber" in err


def test_format_tool_error_generic():
    err = format_tool_error(RuntimeError("Remotion render failed: timeout"))
    assert "RuntimeError" in err
    assert "timeout" in err


def test_validate_required_inputs_transcriber():
    msg = validate_required_inputs(Transcriber(), {})
    assert msg is not None
    assert "transcriber" in msg
    assert "input_path" in msg


def test_validate_required_inputs_subtitle_gen():
    msg = validate_required_inputs(SubtitleGen(), {"format": "srt"})
    assert msg is not None
    assert "subtitle_gen" in msg
    assert "segments" in msg


def test_validate_required_inputs_ok():
    assert validate_required_inputs(SubtitleGen(), {"segments": []}) is None


def test_execute_returns_clear_error_without_keyerror(monkeypatch, tmp_path: Path):
    projects_root = tmp_path / "projects"
    project_dir = projects_root / "demo"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr("plugins.openmontage.lib.events.PROJECTS_DIR", projects_root)
    inputs = {"project_dir": str(project_dir)}
    result = Transcriber().execute(inputs)
    assert result.success is False
    assert result.error
    assert "input_path" in result.error
    assert "缺少必填参数" in result.error
    assert result.error.strip() != "'input_path'"

    events = (project_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    finish = json.loads(events[-1])
    assert finish["event"] == "finish"
    assert finish["success"] is False
    assert "input_path" in finish["error"]


def test_subtitle_gen_execute_clear_error(tmp_path: Path):
    project_dir = tmp_path / "projects" / "demo"
    project_dir.mkdir(parents=True)
    result = SubtitleGen().execute({"project_dir": str(project_dir)})
    assert result.success is False
    assert "segments" in (result.error or "")
