"""Checkpoint / CreateJobQueue E2E Gate 集成代理（TC-CP-01/02/03 · 关页续跑）。"""

from __future__ import annotations

import json

from plugins.mxai.content.create_history import KIND_VIRAL_CLONE, get_history, save_history
from plugins.mxai.content.create_job_queue import (
    complete_job,
    enqueue_jobs,
    list_jobs,
    pick_runnable_jobs,
)
from plugins.mxai.cfg.paths import plugin_state_dir


def test_tc_cp_01_reverse_complete_survives_restart(tmp_path, monkeypatch) -> None:
    """TC-CP-01：reverse 完成后模拟 kill Hub，重开 step_raw 指向可续做阶段。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {
                "title": "镜1",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词用于续做测试",
                "copy": "口播文案",
            },
        ],
        step_raw={"reverse": {"source_copy": {"hook": "你好"}, "mock": True}},
        copy_confirmed=False,
    )
    sid = saved["id"]
    detail = get_history(KIND_VIRAL_CLONE, sid)
    # 单轨：reverse 产物 dict 直存 step_raw（无旧 stage 推断）
    assert isinstance(detail["step_raw"], dict)
    assert detail["step_raw"]["reverse"]["mock"] is True


def test_tc_cp_03_shot_edit_prompt_survives_restart(tmp_path, monkeypatch) -> None:
    """TC-CP-03：shot_edit 改 prompt 后模拟 kill，head 仍保留修改。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {
                "id": "s1",
                "title": "镜1",
                "duration_sec": 5,
                "prompt": "原始提示词足够长用于测试",
                "copy": "",
            },
        ],
        stage_status={"reverse": "done", "shot_edit": "running"},
    )
    sid = saved["id"]
    updated_prompt = "修改后的提示词足够长用于测试续做场景"
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {
                "id": "s1",
                "title": "镜1",
                "duration_sec": 5,
                "prompt": updated_prompt,
                "copy": "",
            },
        ],
    )
    detail = get_history(KIND_VIRAL_CLONE, sid)
    assert detail["shots"][0]["prompt"] == updated_prompt
    head_path = plugin_state_dir() / "create_history" / "sessions" / sid / "head.json"
    assert head_path.is_file()
    head = json.loads(head_path.read_text(encoding="utf-8"))
    # 单轨：step_raw 为产物 dict（无产物时缺省）；状态由 stage_status 表达
    assert head.get("step_raw") is None or isinstance(head.get("step_raw"), dict)
    assert head["stage_status"]["shot_edit"] == "running"


def test_tc_cp_02_generate_jobs_survive_restart(tmp_path, monkeypatch) -> None:
    """TC-CP-02 / 关页续跑：入队 generate 后重载，job 仍在且 depends_on 解锁后续镜。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b"},
        ],
        copy_confirmed=True,
    )
    sid = saved["id"]
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 2

    listed = list_jobs(sid, job_type="generate")
    assert listed["total"] == 2
    jobs = listed["items"]
    assert jobs[1]["depends_on"] == [jobs[0]["job_id"]]

    runnable = pick_runnable_jobs(4)
    assert any(str(j.get("job_id")) == jobs[0]["job_id"] for j in runnable)
    assert not any(str(j.get("job_id")) == jobs[1]["job_id"] for j in runnable)

    complete_job(sid, jobs[0]["job_id"], status="succeeded", result={"shot_id": "1"})
    runnable_after = pick_runnable_jobs(4)
    assert any(str(j.get("job_id")) == jobs[1]["job_id"] for j in runnable_after)
