"""Tool progress lines name the call, never dump raw secrets.

The model supplies a per-call ``label`` (injected into every tool schema by
``tools.registry``). When it does, that label wins. When it doesn't,
``execute_code`` falls back to a short first-line code sniff so the user can
tell what ran — never to the user's own utterance.
"""

from agent.display import (
    _detect_tool_failure,
    build_tool_preview,
    get_cute_tool_message,
    strip_tool_invocation_label,
)


def test_build_tool_preview_prefers_label() -> None:
    preview = build_tool_preview(
        "execute_code",
        {"label": "启动 script 阶段", "code": "import os\n..."},
        max_len=80,
    )
    assert preview == "启动 script 阶段"


def test_build_tool_preview_execute_code_shows_snippet_without_label() -> None:
    preview = build_tool_preview(
        "execute_code",
        {"code": "import os\nos.environ['X']=1"},
        max_len=80,
    )
    assert preview.startswith("import os")
    assert "运行代码" not in preview


def test_label_wins_over_per_tool_branch() -> None:
    line = get_cute_tool_message(
        "om_run",
        {"label": "启动 script 阶段", "project_id": "demo-1", "stage": "script"},
        1.2,
    )
    assert "启动 script 阶段" in line
    assert "demo-1" not in line


def test_om_run_without_label_shows_project_and_stage() -> None:
    line = get_cute_tool_message(
        "om_run",
        {"project_id": "demo-1", "stage": "script"},
        1.2,
    )
    assert "demo-1" in line
    assert "script" in line


def test_execute_code_without_label_shows_code_snippet() -> None:
    line = get_cute_tool_message(
        "execute_code",
        {"code": "import os\nproject_dir = Path('H:/work/OpenMontage')"},
        0.2,
    )
    assert "import os" in line
    assert "运行代码" not in line


def test_execute_code_empty_code_falls_back_to_tool_name() -> None:
    line = get_cute_tool_message("execute_code", {"code": ""}, 0.0)
    assert "运行代码" in line


def test_om_job_without_label_shows_poll_fallback() -> None:
    line = get_cute_tool_message(
        "om_job",
        {"project_id": "my-copy-01", "task_id": "2c4af16de908"},
        0.0,
    )
    assert "轮询任务进度" in line
    assert "2c4af16de908" in line
    assert "om_job" not in line


def test_om_job_with_label_uses_llm_name() -> None:
    line = get_cute_tool_message(
        "om_job",
        {
            "label": "轮询 script 是否完成",
            "project_id": "my-copy-01",
            "task_id": "2c4af16de908",
        },
        0.0,
    )
    assert "轮询 script 是否完成" in line
    assert "2c4af16de908" not in line


def test_strip_tool_invocation_label() -> None:
    cleaned = strip_tool_invocation_label({"label": "x", "code": "print(1)"})
    assert cleaned == {"code": "print(1)"}


def test_detect_tool_failure_ok_true_with_failed_stage_is_not_failure() -> None:
    result = (
        '{"ok": true, "stages": [{"stage": "reference_analysis", '
        '"status": "failed", "error": "aborted"}]}'
    )
    is_failure, _ = _detect_tool_failure("om_project", result)
    assert is_failure is False


def test_detect_tool_failure_ok_false_is_failure() -> None:
    is_failure, suffix = _detect_tool_failure(
        "om_project",
        '{"ok": false, "error": "项目不存在: nope"}',
    )
    assert is_failure is True
    assert "项目不存在" in suffix


def test_cute_message_om_project_success_with_failed_status_no_error_tag() -> None:
    line = get_cute_tool_message(
        "om_project",
        {"label": "读取项目状态", "project_id": "demo"},
        0.1,
        result='{"ok": true, "stages": [{"status": "failed"}]}',
    )
    assert "[error]" not in line
    assert "读取项目状态" in line
