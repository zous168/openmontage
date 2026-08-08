"""The per-call ``label`` instruction reaches the system prompt.

``tools.registry`` injects an optional ``label`` into every tool schema, but
models leave it empty unless the prompt asks for it — and then the tool feed
degrades to raw argument previews. Lean business profiles render the same feed,
so the guidance must survive the ``hermes_help_guidance: false`` gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from agent.prompt_builder import TOOL_INVOCATION_LABEL_GUIDANCE
from agent.system_prompt import build_system_prompt_parts


def _minimal_agent(
    *,
    hermes_help_guidance: bool = True,
    valid_tool_names: set[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        load_soul_identity=False,
        skip_context_files=True,
        valid_tool_names={"terminal", "read_file"} if valid_tool_names is None else valid_tool_names,
        model="gpt-4o",
        provider="openai",
        platform="api_server",
        _task_completion_guidance=True,
        _tool_use_enforcement="auto",
        _hermes_help_guidance=hermes_help_guidance,
        _kanban_worker_guidance=None,
        _memory_store=None,
        _memory_enabled=False,
        _user_profile_enabled=False,
        _memory_manager=None,
        pass_session_id=False,
        session_id=None,
        _environment_probe=False,
    )


def _stable(agent: SimpleNamespace) -> str:
    with patch("run_agent.load_soul_md", return_value=None):
        with patch("run_agent.build_skills_system_prompt", return_value=""):
            return build_system_prompt_parts(agent)["stable"]


def test_label_guidance_present_with_tools() -> None:
    assert TOOL_INVOCATION_LABEL_GUIDANCE in _stable(_minimal_agent())


def test_label_guidance_survives_lean_profile() -> None:
    agent = _minimal_agent(hermes_help_guidance=False)
    assert TOOL_INVOCATION_LABEL_GUIDANCE in _stable(agent)


def test_label_guidance_absent_without_tools() -> None:
    agent = _minimal_agent(valid_tool_names=set())
    assert TOOL_INVOCATION_LABEL_GUIDANCE not in _stable(agent)
