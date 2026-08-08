"""TUI: user-blocking modals must silence live tool chrome.

Evidence: clarify panel + spinner ``(  0.2s)`` stack in the same HSplit;
scrollback ``_cprint`` during modal races prompt_toolkit redraw on Windows.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _bare_cli():
    """HermesCLI without ``__init__`` — only the modal-quiet methods matter."""
    from cli import HermesCLI

    cli = object.__new__(HermesCLI)
    cli._clarify_state = None
    cli._sudo_state = None
    cli._secret_state = None
    cli._approval_state = None
    cli._slash_confirm_state = None
    cli._spinner_text = "⏳ 等 90 秒查进度"
    cli._tool_start_time = 123.0
    cli._pending_tool_info = {}
    cli._last_scrollback_tool = ""
    cli.tool_progress_mode = "all"
    cli._long_tool_hint_fired = True
    cli._invalidate = MagicMock()
    return cli


def test_clarify_modal_hides_spinner_text():
    cli = _bare_cli()
    assert "0." in cli._render_spinner_text() or "等" in cli._render_spinner_text()

    cli._quiet_tool_chrome_for_modal()
    cli._clarify_state = {"question": "挑一个", "choices": ["A", "B"], "selected": 0}

    assert cli._user_blocking_modal_active() is True
    assert cli._render_spinner_text() == ""
    assert cli._spinner_text == ""
    assert cli._tool_start_time == 0.0


def test_tool_progress_muted_during_clarify(monkeypatch):
    cli = _bare_cli()
    cli._clarify_state = {"question": "?", "choices": [], "selected": 0}

    printed: list[str] = []
    monkeypatch.setattr("cli._cprint", lambda text: printed.append(text))

    before = cli._spinner_text
    cli._on_tool_progress(
        "tool.started",
        function_name="om_job",
        preview="轮询 research",
        function_args={"label": "轮询 research"},
    )
    # Live chrome stays suppressed (render empty); do not promote a new spinner.
    assert cli._render_spinner_text() == ""
    assert cli._spinner_text == before
    assert "om_job" in cli._pending_tool_info

    cli._on_tool_progress(
        "tool.completed",
        function_name="om_job",
        duration=0.2,
        result='{"status":"running"}',
    )
    assert printed == []
    assert "om_job" not in cli._pending_tool_info


def test_tool_progress_prints_when_no_modal(monkeypatch):
    cli = _bare_cli()
    cli._spinner_text = ""
    cli._tool_start_time = 0.0

    printed: list[str] = []
    monkeypatch.setattr("cli._cprint", lambda text: printed.append(text))

    with patch("agent.display.get_cute_tool_message", return_value="┊ om_job ok  0.2s"):
        cli._on_tool_progress(
            "tool.started",
            function_name="om_job",
            preview="轮询",
            function_args={"label": "轮询"},
        )
        assert cli._spinner_text  # live chrome allowed
        cli._on_tool_progress(
            "tool.completed",
            function_name="om_job",
            duration=0.2,
            result="{}",
        )

    assert any("om_job" in line or "┊" in line for line in printed)
