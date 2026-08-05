"""Cron job storage follows the active profile scope."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.profile_scope import hermes_profile_scope
from cron.jobs import create_job, list_jobs


@pytest.fixture
def hub_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "hub"
    root.mkdir()
    assistant = root / "profiles" / "assistant"
    assistant.mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    return root


def test_create_job_under_assistant_profile(hub_root: Path) -> None:
    assistant_home = hub_root / "profiles" / "assistant"

    with hermes_profile_scope(assistant_home):
        job = create_job(prompt="assistant reminder", schedule="30m", name="from-assistant")

    jobs_file = assistant_home / "cron" / "jobs.json"
    assert jobs_file.is_file()
    assert job["id"]
    with hermes_profile_scope(assistant_home):
        stored = list_jobs()
    assert len(stored) == 1
    assert stored[0]["id"] == job["id"]
    assert stored[0]["name"] == "from-assistant"

    default_jobs = hub_root / "cron" / "jobs.json"
    assert not default_jobs.exists()


def test_list_job_outputs_includes_failed_and_ok(hub_root: Path) -> None:
    from agent.profile_scope import hermes_profile_scope
    from cron.jobs import _job_output_dir, create_job, list_job_outputs

    assistant_home = hub_root / "profiles" / "assistant"
    with hermes_profile_scope(assistant_home):
        job = create_job(prompt="ping", schedule="30m", name="hist-test")
        out_dir = _job_output_dir(job["id"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "2026-07-02_18-00-01.md").write_text(
            "# Cron Job: hist-test (FAILED)\n\n## Error\n\n```\nmodel empty\n```\n",
            encoding="utf-8",
        )
        (out_dir / "2026-07-02_18-00-02.md").write_text(
            "# Cron Job: hist-test\n\n## Response\n\npong\n",
            encoding="utf-8",
        )

    with hermes_profile_scope(assistant_home):
        outputs = list_job_outputs(job["id"])

    assert len(outputs) == 2
    statuses = {output["status"] for output in outputs}
    assert statuses == {"ok", "failed"}


def test_create_job_under_default_profile(hub_root: Path) -> None:
    with hermes_profile_scope(hub_root):
        job = create_job(prompt="default reminder", schedule="1h")

    jobs_file = hub_root / "cron" / "jobs.json"
    assert jobs_file.is_file()
    with hermes_profile_scope(hub_root):
        stored = list_jobs()
    assert len(stored) == 1
    assert stored[0]["id"] == job["id"]
