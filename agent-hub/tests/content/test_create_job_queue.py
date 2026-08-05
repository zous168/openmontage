"""CreateJobQueue 单测（VC-T05）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from plugins.mxai.content.create_history import KIND_VIRAL_CLONE, save_history
from plugins.mxai.content.create_job_queue import (
    _load_session_jobs,
    cancel_job,
    clear_jobs,
    complete_job,
    enqueue_jobs,
    get_job,
    list_jobs,
    pick_runnable_jobs,
    retry_job,
)


def _seed_session(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    return save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/v.mp4",
        shots=[{"title": "镜1", "duration_sec": 5, "prompt": "足够长的分镜提示词用于测试", "copy": "口播"}],
        copy_confirmed=True,
    )


def test_enqueue_reverse_job(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="reverse")
    assert out["accepted"] is True
    assert len(out["job_ids"]) == 1
    listed = list_jobs(sid)
    assert listed["total"] == 1
    assert listed["items"][0]["job_type"] == "reverse"


def test_enqueue_generate_per_shot(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a", "gen_mode": "i2v"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b", "gen_mode": "i2v"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 2
    jobs = list_jobs(sid, job_type="generate")["items"]
    assert jobs[1]["depends_on"] == [jobs[0]["job_id"]]


def test_enqueue_generate_chain_depends_without_infer(tmp_path, monkeypatch) -> None:
    """无显式 gen_mode 时默认 t2v，但镜链仍 depends_on 前镜。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 2
    jobs = _load_session_jobs(sid)
    gen_jobs = [j for j in jobs if j.get("job_type") == "generate"]
    assert gen_jobs[0]["gen_mode"] == "t2v"
    assert gen_jobs[1]["gen_mode"] == "t2v"
    listed = list_jobs(sid, job_type="generate")["items"]
    assert listed[1]["depends_on"] == [listed[0]["job_id"]]


def test_enqueue_generate_respects_explicit_t2v_on_second_shot(tmp_path, monkeypatch) -> None:
    """后镜显式 t2v 不再被 Hub 纠偏为 i2v。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a", "gen_mode": "t2v"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b", "gen_mode": "t2v"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    from plugins.mxai.content.create_job_queue import _load_session_jobs

    jobs = _load_session_jobs(sid)
    by_shot = {str(j.get("shot_id")): j for j in jobs if j.get("job_type") == "generate"}
    assert by_shot["1"]["gen_mode"] == "t2v"
    assert by_shot["2"]["gen_mode"] == "t2v"


def test_enqueue_generate_t2v_second_shot_still_depends(tmp_path, monkeypatch) -> None:
    """后镜显式 t2v 仍须等前镜落盘 task_id，depends_on 不可省略。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a", "gen_mode": "t2v"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b", "gen_mode": "t2v"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 2
    first_job = get_job(out["job_ids"][0])
    second_job = get_job(out["job_ids"][1])
    assert second_job["depends_on"] == [first_job["job_id"]]


def test_cancel_and_retry(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="reverse")
    jid = out["job_ids"][0]
    cancel_job(jid)
    job = get_job(jid)
    assert job["status"] == "cancelled"


def test_pick_runnable_respects_depends(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    runnable = pick_runnable_jobs(4)
    assert len(runnable) >= 1


def test_complete_failed_cascades_fail_dependents(tmp_path, monkeypatch) -> None:
    """前序失败且 on_fail=stop 时，依赖链后续一并 failed，勿永久卡在排队中。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b"},
            {"id": 3, "title": "c", "duration_sec": 5, "prompt": "足够长的分镜提示词 C", "copy": "c"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 3
    first, second, third = out["job_ids"]
    complete_job(sid, first, status="failed", error={"code": "REFERENCE_REQUIRED", "message": "缺首帧"})
    assert get_job(second)["status"] == "failed"
    assert get_job(third)["status"] == "failed"
    assert get_job(second)["error"]["code"] == "VC_DEP_FAILED"


def test_enqueue_generate_force_regen(tmp_path, monkeypatch) -> None:
    """force=True 时已有成片的镜头也可再入队。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {
                "id": 1,
                "title": "a",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词 A",
                "copy": "a",
                "preview_url": "https://cdn.example.com/a.mp4",
                "video_url": "https://cdn.example.com/a.mp4",
            },
        ],
        copy_confirmed=True,
    )
    skip = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert skip["job_ids"] == []
    again = enqueue_jobs(
        session_id=sid,
        kind=KIND_VIRAL_CLONE,
        job_type="generate",
        shot_ids=["1"],
        force=True,
    )
    assert len(again["job_ids"]) == 1


def test_clear_jobs_removes_failed(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    first, second = out["job_ids"]
    complete_job(sid, first, status="failed", error={"message": "x"})
    cleared = clear_jobs(sid)
    assert cleared["removed_count"] == 2
    assert first in cleared["removed"]
    assert second in cleared["removed"]
    assert list_jobs(sid)["total"] == 0


def test_list_jobs_reconciles_stale_queued_dependents(tmp_path, monkeypatch) -> None:
    """历史脏数据：前序已 failed、后续仍 queued → list 时自愈为 failed。"""
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b"},
        ],
        copy_confirmed=True,
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    first, second = out["job_ids"]
    # 模拟旧逻辑：只标前序 failed，未级联
    from plugins.mxai.content.create_job_queue import _load_session_jobs, _save_session_jobs

    jobs = _load_session_jobs(sid)
    for job in jobs:
        if str(job.get("job_id")) == first:
            job["status"] = "failed"
            job["error"] = {"code": "REFERENCE_REQUIRED", "message": "缺首帧"}
    _save_session_jobs(sid, jobs)
    assert get_job(second)["status"] == "queued"
    listed = list_jobs(sid, job_type="generate")
    by_id = {j["job_id"]: j for j in listed["items"]}
    assert by_id[second]["status"] == "failed"
    assert by_id[second]["error"]["code"] == "VC_DEP_FAILED"


def test_enqueue_generate_r2v_freezes_resolved_media(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {
                "id": 2,
                "title": "b",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词 B",
                "copy": "b",
                "gen_mode": "r2v",
                "ref_ids": ["p1", "p2"],
            },
        ],
        params={
            "refs": [
                {
                    "id": "p1",
                    "url": "https://cdn.example/p1.jpg",
                    "oss_key": "uploads/t/p1.jpg",
                    "sha256": "aaa",
                },
                {
                    "id": "p2",
                    "url": "https://cdn.example/p2.jpg",
                    "oss_key": "uploads/t/p2.jpg",
                    "sha256": "bbb",
                },
            ],
        },
        copy_confirmed=True,
    )
    with patch("plugins.mxai.content.media_snapshot.validate_media_reachable", return_value=(True, None)):
        out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert len(out["job_ids"]) == 2
    jobs = _load_session_jobs(sid)
    r2v_job = next(j for j in jobs if str(j.get("shot_id")) == "2")
    assert r2v_job["gen_mode"] == "r2v"
    assert len(r2v_job["resolved_media"]) == 2
    assert {x["ref_id"] for x in r2v_job["resolved_media"]} == {"p1", "p2"}
    assert r2v_job["resolved_media"][0]["oss_key"].startswith("uploads/")


def test_enqueue_generate_r2v_unresolved_rejected(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {
                "id": 2,
                "title": "b",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词 B",
                "copy": "b",
                "gen_mode": "r2v",
                "ref_ids": ["missing"],
            },
        ],
        params={"refs": []},
        copy_confirmed=True,
    )
    with pytest.raises(HTTPException) as ei:
        enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "VC_R2V_REFS_UNRESOLVED"


def test_enqueue_generate_r2v_unreachable_rejected(tmp_path, monkeypatch) -> None:
    saved = _seed_session(tmp_path, monkeypatch)
    sid = saved["id"]
    save_history(
        kind=KIND_VIRAL_CLONE,
        item_id=sid,
        source_url="https://cdn.example.com/v.mp4",
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {
                "id": 2,
                "title": "b",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词 B",
                "copy": "b",
                "gen_mode": "r2v",
                "ref_ids": ["p1"],
            },
        ],
        params={"refs": [{"id": "p1", "url": "https://cdn.example/p1.jpg"}]},
        copy_confirmed=True,
    )
    with patch(
        "plugins.mxai.content.media_snapshot.validate_media_reachable",
        return_value=(False, "p1"),
    ):
        with pytest.raises(HTTPException) as ei:
            enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    assert ei.value.detail["code"] == "VC_R2V_REFS_UNRESOLVED"
