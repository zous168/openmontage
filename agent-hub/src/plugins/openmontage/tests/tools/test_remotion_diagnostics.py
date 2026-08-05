"""Tests for Remotion render debuggability in video_compose (issue #217).

Two creator-facing gaps:
  1. A failed `npx remotion render` surfaced only "returned non-zero exit
     status 1"; the useful Remotion diagnostics in stderr were dropped.
  2. There was no pass-through for Remotion's `--timeout`, so a slow headless
     browser setup failed opaquely with no way to raise the limit.
"""

import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from plugins.openmontage.tools.video.video_compose import VideoCompose  # noqa: E402


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/npx")
    return VideoCompose()


def _make_project(tmp_path):
    """Turn tmp_path into a valid project dir so _remotion_render proceeds past
    the public-dir inference step (renders/<id>/out.mp4 layout)."""
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "renders" / "out.mp4"
    out.parent.mkdir(parents=True)
    return out


def test_render_failure_surfaces_remotion_stderr_tail(tool, tmp_path, monkeypatch):
    stderr = "some npm noise\nError: Delayed render timed out\nRemotion actual cause here"
    out = _make_project(tmp_path)

    def fake_run_command(cmd, *a, **k):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr=stderr)

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    result = tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(out)}
    )

    assert result.success is False
    assert "exit 1" in result.error
    assert "Remotion actual cause here" in result.error


def test_timeout_expired_gives_actionable_message(tool, tmp_path, monkeypatch):
    out = _make_project(tmp_path)

    def fake_run_command(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=600)

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    result = tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(out)}
    )

    assert result.success is False
    assert "timed out" in result.error.lower()
    assert "remotion_timeout_ms" in result.error


def test_remotion_timeout_ms_is_passed_through(tool, tmp_path, monkeypatch):
    seen = {}
    out = _make_project(tmp_path)

    def fake_run_command(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["timeout"] = k.get("timeout")
        return None  # output file intentionally absent

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    tool._remotion_render(
        {
            "composition_data": {"cuts": []},
            "output_path": str(out),
            "remotion_timeout_ms": 120000,
        }
    )

    # render.mjs uses equals-form args; the legacy npx path uses a pair.
    assert any(str(a).startswith("--timeout") and "120000" in str(a) for a in seen["cmd"])
    # subprocess timeout widened past the 120s render budget so run_command
    # does not kill Remotion before its own timeout fires.
    assert seen["timeout"] >= 180


def test_high_level_render_forwards_timeout_to_remotion(tool, tmp_path, monkeypatch):
    # The gap in the first cut: execute(operation="render") -> _render() builds a
    # fresh remotion_inputs dict, so the option must be forwarded there, not only
    # on a direct _remotion_render() call.
    captured = {}
    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *a, **k: None)
    monkeypatch.setattr(tool, "_needs_remotion", lambda *a, **k: True)

    def fake_remotion_render(inputs):
        captured.update(inputs)
        from plugins.openmontage.tools.base_tool import ToolResult

        return ToolResult(success=True, data={}, artifacts=[])

    monkeypatch.setattr(tool, "_remotion_render", fake_remotion_render)
    monkeypatch.setattr(tool, "_run_final_review", lambda *a, **k: {})

    tool._render(
        {
            "edit_decisions": {
                "render_runtime": "remotion",
                "renderer_family": "explainer-data",
                "cuts": [{"id": "c1", "source": "a1", "in_seconds": 0, "out_seconds": 2}],
            },
            "asset_manifest": {"assets": [{"id": "a1", "path": "/tmp/a1.mp4"}]},
            "output_path": str(tmp_path / "out.mp4"),
            "remotion_timeout_ms": 120000,
        }
    )

    assert captured.get("remotion_timeout_ms") == 120000


def test_no_timeout_flag_when_not_requested(tool, tmp_path, monkeypatch):
    seen = {}
    out = _make_project(tmp_path)

    def fake_run_command(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["timeout"] = k.get("timeout")
        return None

    monkeypatch.setattr(tool, "run_command", fake_run_command)
    tool._remotion_render(
        {"composition_data": {"cuts": []}, "output_path": str(out)}
    )

    assert not any(str(c).startswith("--timeout") for c in seen["cmd"])
    assert seen["timeout"] == 600
