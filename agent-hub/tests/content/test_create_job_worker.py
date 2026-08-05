"""CreateJobWorker 启动与 generate 续写参数校验。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from plugins.mxai.content.create_history import KIND_VIRAL_CLONE, save_history
from plugins.mxai.content.create_job_queue import enqueue_jobs, get_job
from plugins.mxai.content.create_job_worker import (
    CreateJobWorker,
    _format_generate_ref_trace,
    _job_error_from_exc,
)


def test_worker_start_no_name_error() -> None:
    worker = CreateJobWorker.get()
    worker.start()
    assert worker._running is True
    worker.stop()
    assert worker._running is False


def test_format_generate_ref_trace_prev_video() -> None:
    trace = _format_generate_ref_trace(
        img_url="data:image/jpeg;base64,abc",
        previous_video_id="rpavid_prev1",
        prev_video_url="https://cdn.example.com/a.mp4",
        result={
            "reference_source": "prev_video",
            "reference_image": "data:image/jpeg;base64,abc",
            "img_url": "data:image/…;base64,(12 chars)",
        },
    )
    assert trace["has_reference"] is True
    assert trace["reference_source"] == "prev_video"
    assert "previous_video_id: rpavid_prev1" in trace["image_refs"]
    assert "首帧来自上一镜成片尾帧" in trace["image_refs"]


def test_format_generate_ref_trace_t2v_none() -> None:
    trace = _format_generate_ref_trace(
        img_url=None,
        previous_video_id="rpavid_prev1",
        prev_video_url=None,
        result={"reference_source": "none"},
    )
    assert trace["has_reference"] is False
    assert "无首帧参考" in trace["image_refs"]
    assert "previous_video_id: rpavid_prev1" in trace["image_refs"]

    err = _job_error_from_exc(
        ValueError("VC_I2V_NO_FIRST_FRAME: 无法从上一镜成片抽取首帧参考")
    )
    assert err == {
        "code": "VC_I2V_NO_FIRST_FRAME",
        "message": "无法从上一镜成片抽取首帧参考",
    }


def _seed_two_shots(tmp_path, monkeypatch, *, shots: list[dict]) -> str:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    saved = save_history(
        kind=KIND_VIRAL_CLONE,
        source_url="https://cdn.example.com/v.mp4",
        shots=shots,
        copy_confirmed=True,
    )
    return str(saved["id"])


@pytest.mark.asyncio
async def test_generate_missing_previous_video_id_fails(tmp_path, monkeypatch) -> None:
    sid = _seed_two_shots(
        tmp_path,
        monkeypatch,
        shots=[
            {"id": 1, "title": "a", "duration_sec": 5, "prompt": "足够长的分镜提示词 A", "copy": "a"},
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b", "gen_mode": "t2v"},
        ],
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    second_job = get_job(out["job_ids"][1])
    worker = CreateJobWorker.get()
    catalog = {"items": [{"model_name": "mock-t2v"}, {"model_name": "mock-i2v"}]}
    with patch(
        "plugins.mxai.content.create_job_worker.list_gateway_models",
        return_value=catalog,
    ):
        with pytest.raises(ValueError, match="PREVIOUS_VIDEO_ID_REQUIRED"):
            await worker._execute(second_job, KIND_VIRAL_CLONE, "generate", sid)


@pytest.mark.asyncio
async def test_generate_i2v_without_first_frame_fails(tmp_path, monkeypatch) -> None:
    sid = _seed_two_shots(
        tmp_path,
        monkeypatch,
        shots=[
            {
                "id": 1,
                "title": "a",
                "duration_sec": 5,
                "prompt": "足够长的分镜提示词 A",
                "copy": "a",
                "task_id": "rpavid_prev123",
            },
            {"id": 2, "title": "b", "duration_sec": 5, "prompt": "足够长的分镜提示词 B", "copy": "b", "gen_mode": "i2v"},
        ],
    )
    out = enqueue_jobs(session_id=sid, kind=KIND_VIRAL_CLONE, job_type="generate")
    second_job = get_job(out["job_ids"][1])
    worker = CreateJobWorker.get()
    catalog = {"items": [{"model_name": "mock-t2v"}, {"model_name": "mock-i2v"}]}
    with patch(
        "plugins.mxai.content.create_job_worker.list_gateway_models",
        return_value=catalog,
    ):
        with patch(
            "plugins.mxai.content.create_job_worker.resolve_reference_image",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="VC_I2V_NO_FIRST_FRAME"):
                await worker._execute(second_job, KIND_VIRAL_CLONE, "generate", sid)
