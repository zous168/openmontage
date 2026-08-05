"""Contract tests: get_status() must match execute() runtime requirements."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import shutil

from plugins.openmontage.tools.analysis.face_tracker import FaceTracker
from plugins.openmontage.tools.avatar.lip_sync import LipSync, MODEL_CHECKPOINTS
from plugins.openmontage.tools.avatar.talking_head import TalkingHead
from plugins.openmontage.tools.base_tool import ToolStatus
from plugins.openmontage.tools.graphics.diagram_gen import DiagramGen
from plugins.openmontage.tools.graphics.math_animate import MathAnimate


class TestFaceTrackerStatus:
    def test_unavailable_without_opencv(self, monkeypatch):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "cv2":
                raise ImportError("No module named 'cv2'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert FaceTracker().get_status() == ToolStatus.UNAVAILABLE

    def test_degraded_with_opencv_only(self, monkeypatch):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "mediapipe":
                raise ImportError("No module named 'mediapipe'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        status = FaceTracker().get_status()
        assert status in (ToolStatus.AVAILABLE, ToolStatus.DEGRADED, ToolStatus.UNAVAILABLE)
        if status != ToolStatus.UNAVAILABLE:
            assert status == ToolStatus.DEGRADED


class TestLipSyncStatus:
    def test_unavailable_without_wav2lip_tree(self, monkeypatch):
        monkeypatch.delenv("WAV2LIP_PATH", raising=False)
        monkeypatch.setattr(
            LipSync,
            "_resolve_wav2lip_dir",
            lambda self: None,
        )
        assert LipSync().get_status() == ToolStatus.UNAVAILABLE

    def test_unavailable_when_checkpoint_missing(self, monkeypatch, tmp_path):
        repo = tmp_path / "wav2lip"
        (repo / "checkpoints").mkdir(parents=True)
        (repo / "inference.py").write_text("# stub", encoding="utf-8")
        monkeypatch.setattr(LipSync, "_resolve_wav2lip_dir", lambda self: repo)
        assert LipSync().get_status() == ToolStatus.UNAVAILABLE

    def test_available_when_runtime_ready(self, monkeypatch, tmp_path):
        repo = tmp_path / "wav2lip"
        ckpt_dir = repo / "checkpoints"
        ckpt_dir.mkdir(parents=True)
        (repo / "inference.py").write_text("# stub", encoding="utf-8")
        (ckpt_dir / MODEL_CHECKPOINTS["wav2lip"]).write_bytes(b"x")
        monkeypatch.setattr(LipSync, "_resolve_wav2lip_dir", lambda self: repo)
        assert LipSync().get_status() == ToolStatus.AVAILABLE


class TestTalkingHeadStatus:
    def test_unavailable_without_inference_script(self, monkeypatch, tmp_path):
        repo = tmp_path / "sadtalker"
        repo.mkdir()
        monkeypatch.setenv("SADTALKER_PATH", str(repo))
        assert TalkingHead().get_status() == ToolStatus.UNAVAILABLE

    def test_available_with_inference_script(self, monkeypatch, tmp_path):
        repo = tmp_path / "sadtalker"
        repo.mkdir()
        (repo / "inference.py").write_text("# stub", encoding="utf-8")
        monkeypatch.setenv("SADTALKER_PATH", str(repo))
        assert TalkingHead().get_status() == ToolStatus.AVAILABLE


class TestDiagramGenStatus:
    def test_degraded_with_pillow_only(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        tool = DiagramGen()
        if tool._has_pillow():
            assert tool.get_status() == ToolStatus.DEGRADED
        else:
            assert tool.get_status() == ToolStatus.UNAVAILABLE

    def test_available_with_mmdc(self, monkeypatch):
        monkeypatch.setattr(
            shutil,
            "which",
            lambda cmd: "/usr/bin/mmdc" if cmd == "mmdc" else None,
        )
        assert DiagramGen().get_status() == ToolStatus.AVAILABLE


class TestMathAnimateStatus:
    def test_unavailable_when_python_module_missing(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "manim":
                raise ImportError("No module named 'manim'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert MathAnimate().get_status() == ToolStatus.UNAVAILABLE

    def test_available_via_python_module_without_cli(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "manim":
                return MagicMock()
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert MathAnimate().get_status() == ToolStatus.AVAILABLE

    def test_manim_command_prefix_falls_back_to_module(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "manim":
                return MagicMock()
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        prefix = MathAnimate._manim_command_prefix()
        assert len(prefix) >= 2
        assert prefix[-2:] == ["-m", "manim"] or prefix == ["manim"]
