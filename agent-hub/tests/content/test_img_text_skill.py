"""ImgTextVideoRunner 全链路 mock 测试（LT-052 M5 审核修复）。

覆盖：save_params 校验、generate_shots 落 history、rewrite_copy next_step=generate_videos、
generate_videos 确认门与入队（kind=img_text）、export_capcut 正确签名（tracks 校验/voice skipped 标记）、
list_history dict 消费、check_project 续做恢复 compose_plan。
"""

from __future__ import annotations

from plugins.mxai.content.create_history import get_history
from plugins.mxai.content.create_job_queue import _load_session_jobs
from skills.mxai.img_text_video import ImgTextVideoRunner, run


def _runner(tmp_path, monkeypatch, session_id: str = "it-session-001") -> ImgTextVideoRunner:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    return ImgTextVideoRunner(session_id=session_id)


def _seed(tmp_path, monkeypatch, session_id: str = "it-session-001", **extra) -> ImgTextVideoRunner:
    runner = _runner(tmp_path, monkeypatch, session_id=session_id)
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=30, aspect_ratio="9:16", appear_mode="walk", **extra,
    )
    assert result.ok, result.error
    return runner


async def _fake_planner(params, model=None, instruction=None, session_id=None):
    return {
        "shots": [
            {"id": "1", "title": "开场钩子", "duration_sec": 10, "copy": "口播1",
             "prompt": "工厂开场", "shot_type": "talking_head", "gen_mode": "t2v"},
            {"id": "2", "title": "卖点承接", "duration_sec": 10, "copy": "口播2",
             "prompt": "工艺展示", "shot_type": "talking_head", "gen_mode": "i2v"},
            {"id": "3", "title": "CTA", "duration_sec": 10, "copy": "口播3",
             "prompt": "收束", "shot_type": "talking_head", "gen_mode": "i2v"},
        ],
        "sections": [{"key": "copy_blocks", "title": "文案区块", "fields": []}],
        "source_copy": {"full_script": "口播全文", "hook": "钩子", "cta": "CTA"},
        "meta": {"total_duration_sec": 30, "segment_sec": 10, "segment_count": 3},
        "mock": True,
    }


def _seed_with_shots(tmp_path, monkeypatch, session_id: str = "it-session-001") -> ImgTextVideoRunner:
    runner = _seed(tmp_path, monkeypatch, session_id=session_id)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    result = runner.run("generate_shots")
    assert result.ok, result.error
    return runner


# ============================================================================
# save_params / generate_shots
# ============================================================================

def test_save_params_lands_history(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    detail = get_history("img_text", runner.session_id)
    assert detail["kind"] == "img_text"
    assert detail["params"]["product"] == "玻璃杯"
    assert detail["stage_status"]["params"] == "done"


# ============================================================================
# 参数契约校验（LT-053 M1.01：%10/枚举/refs/identity_source）
# ============================================================================

def test_save_params_duration_not_multiple_of_10_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=35, aspect_ratio="9:16", appear_mode="walk",
    )
    assert result.ok is False
    assert "10 的倍数" in (result.error or "")


def test_save_params_duration_out_of_range_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=5, aspect_ratio="9:16", appear_mode="walk",
    )
    assert result.ok is False
    assert "10 的倍数" in (result.error or "")


def test_save_params_invalid_enum_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    # scene 非法
    result = runner.run(
        "save_params", product="玻璃杯", scene="roof", video_form="talking_head",
        duration_sec=30, aspect_ratio="9:16", appear_mode="walk",
    )
    assert result.ok is False
    assert "scene" in (result.error or "")
    # content_style 非法：拒绝而非静默回落 ugc
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=30, aspect_ratio="9:16", appear_mode="walk", content_style="weird",
    )
    assert result.ok is False
    assert "content_style" in (result.error or "")


def test_save_params_refs_invalid_role_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=30, aspect_ratio="9:16", appear_mode="walk",
        refs=[{"id": "r1", "url": "https://cdn.example.com/p.png", "role": "avatar"}],
    )
    assert result.ok is False
    assert "role" in (result.error or "")


def test_save_params_refs_over_12_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    refs = [{"id": f"r{i}", "url": f"https://cdn.example.com/{i}.png", "role": "product"} for i in range(13)]
    result = runner.run(
        "save_params", product="玻璃杯", scene="factory", video_form="talking_head",
        duration_sec=30, aspect_ratio="9:16", appear_mode="walk", refs=refs,
    )
    assert result.ok is False
    assert "12" in (result.error or "")


def test_save_params_identity_source_derived(tmp_path, monkeypatch) -> None:
    # 含人物参考图 → photo_lock
    runner = _seed(
        tmp_path, monkeypatch, session_id="it-identity-1",
        refs=[{"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character"}],
    )
    assert runner.state["params"]["identity_source"] == "photo_lock"

    # 仅产品参考图 → ai_gen
    runner = _seed(
        tmp_path, monkeypatch, session_id="it-identity-2",
        refs=[{"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"}],
    )
    assert runner.state["params"]["identity_source"] == "ai_gen"

    # 无 refs → ai_gen（默认）
    runner = _seed(tmp_path, monkeypatch, session_id="it-identity-3")
    assert runner.state["params"]["identity_source"] == "ai_gen"

    # 显式覆盖
    runner = _seed(
        tmp_path, monkeypatch, session_id="it-identity-4",
        refs=[{"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"}],
        identity_source="photo_lock",
    )
    assert runner.state["params"]["identity_source"] == "photo_lock"


def test_generate_shots_lands_history(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    detail = get_history("img_text", runner.session_id)
    assert detail["shots"]
    assert detail["stage_status"]["reverse"] == "done"


# ============================================================================
# rewrite_copy → next_step=generate_videos（M5 F3）
# ============================================================================

def test_rewrite_copy_next_step_generate_videos(monkeypatch, tmp_path) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)

    def fake(source_copy, shots, instruction=None, session_id=None):
        return {"shots": [{"copy": f"新口播-{s.get('id')}"} for s in shots], "source_copy": source_copy, "mock": True}

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy", instruction="更幽默一点")
    assert result.ok, result.error
    assert result.next_step == "generate_videos"
    assert result.needs_confirmation is False  # 确认卡收敛到 generate_videos 动作


# ============================================================================
# generate_videos — 确认门 + 入队（M5 F3）
# ============================================================================

def test_generate_videos_first_call_needs_confirmation(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    result = runner.run("generate_videos")
    assert result.ok
    assert result.needs_confirmation is True
    card = result.confirmation_card
    assert card and card["title"] == "开始生成视频"
    assert "镜" in card["description"]


def test_generate_videos_confirmed_enqueues(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    result = runner.run("generate_videos", confirmed=True, generate_model_pref="demo-t2v")
    assert result.ok, result.error
    assert result.data["job_ids"]
    jobs = _load_session_jobs(runner.session_id)
    assert jobs and str(jobs[0].get("kind")) == "img_text"


def test_generate_videos_without_shots_rejected(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    result = runner.run("generate_videos")
    assert result.ok is False
    assert "分镜" in (result.error or "")


# ============================================================================
# export_capcut — 正确签名 / tracks 校验 / voice skipped（M5 F1）
# ============================================================================

def test_export_capcut_full_flow(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    result = runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error
    assert result.data["draft_path"]

    detail = get_history("img_text", runner.session_id)
    ss = detail["stage_status"]
    assert ss["voice"] == "skipped"
    assert ss["compose"] == "done"
    legacy = detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}
    voice_mark = legacy.get("voice")
    assert voice_mark and voice_mark.get("skipped") is True


def test_export_capcut_missing_plan_rejected(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    result = runner.run("export_capcut")
    assert result.ok is False
    assert "tracks" in (result.error or "")


# ============================================================================
# list_history — dict 消费（M5 F2）
# ============================================================================

def test_list_history_shows_project(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    result = runner.run("list_history")
    assert result.ok
    assert result.data["items"]
    assert result.data["items"][0]["product"] == "玻璃杯"


def test_list_history_empty(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch, session_id="it-empty")
    result = runner.run("list_history")
    assert result.ok
    assert result.data["items"] == []


# ============================================================================
# check_project — 续做恢复 compose_plan（M5 F6）
# ============================================================================

def test_check_project_resume_restores_compose_plan(tmp_path, monkeypatch) -> None:
    runner = _seed_with_shots(tmp_path, monkeypatch)
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))

    # 新 runner 实例续做：compose_plan 从 history 恢复
    resumed = _runner(tmp_path, monkeypatch, session_id=runner.session_id)
    result = resumed.run("check_project")
    assert result.ok
    assert result.data["has_project"] is True
    assert resumed.state["compose_plan"].get("tracks")


def test_check_project_no_project(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is False


# ============================================================================
# 入口
# ============================================================================

def test_module_run_entry_dict_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = run(
        session_id="it-entry-001", action="save_params", product="玻璃杯", scene="factory",
        video_form="talking_head", duration_sec=30, aspect_ratio="9:16", appear_mode="walk",
    )
    assert out["ok"] is True
    assert out["stage"] == "reverse"
    assert out["next_step"] == "generate_shots"
