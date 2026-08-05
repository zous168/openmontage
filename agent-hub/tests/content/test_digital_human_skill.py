"""DigitalHumanVideoRunner 全链路 mock 测试 (LT-052 M3.03 + LT-054 升级).

覆盖：save_params 校验（avatar_ref / voice_id 必填 / duration_sec 10 的倍数）、
generate_shots 落 history(kind=digital_human, params-only 无 source_url) + 数字人口播指令注入、
rewrite_copy、generate_videos 确认门与入队、check_job_status、list_voices、
synthesize_voice（TTS 写回 shots）、export_capcut（TTS 入片 note 条件化）、
list_history、check_project 续做。
"""

from __future__ import annotations

from plugins.mxai.content.create_history import get_history
from plugins.mxai.content.create_job_queue import _load_session_jobs
from skills.mxai.digital_human_video import DigitalHumanVideoRunner, run
from skills.mxai.digital_human_video import run as run_digital_human_video_skill

_AVATAR = {"id": "a1", "url": "https://cdn.example.com/avatar.png"}
_VOICE_ID = "sys_default_female"


def _runner(tmp_path, monkeypatch, session_id: str = "dh-session-001") -> DigitalHumanVideoRunner:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    return DigitalHumanVideoRunner(session_id=session_id)


def _seed(tmp_path, monkeypatch, session_id: str = "dh-session-001", **extra) -> DigitalHumanVideoRunner:
    runner = _runner(tmp_path, monkeypatch, session_id=session_id)
    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id=_VOICE_ID, **extra,
    )
    assert result.ok, result.error
    return runner


# ============================================================================
# save_params 校验分支
# ============================================================================

def test_save_params_missing_avatar_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("save_params", product="玻璃杯", scene="indoor", duration_sec=30, aspect_ratio="9:16")
    assert result.ok is False
    assert "avatar_ref" in (result.error or "")


def test_save_params_missing_voice_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="9:16", avatar_ref=_AVATAR,
    )
    assert result.ok is False
    assert "voice_id" in (result.error or "")


def test_save_params_invalid_voice_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id="no-such-voice",
    )
    assert result.ok is False
    assert "voice_id" in (result.error or "")


def test_save_params_duration_not_multiple_of_10_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=35,
        aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id=_VOICE_ID,
    )
    assert result.ok is False
    assert "10 的倍数" in (result.error or "")


def test_save_params_lands_history_params_only(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    detail = get_history("digital_human", runner.session_id)
    assert detail["kind"] == "digital_human"
    assert detail["params"]["product"] == "玻璃杯"
    assert detail["params"]["avatar_ref"]["role"] == "character"
    assert detail["params"]["voice_id"] == _VOICE_ID
    assert detail["params"]["voice_name"]  # 由音色库回填
    assert detail["stage_status"]["params"] == "done"
    # 无 source_url 的 params-only 保存放行（allow_no_url 扩展点）
    assert not (detail.get("source_url") or "")


def test_save_params_avatar_url_string_normalized(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch, session_id="dh-avatar-str")
    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="9:16", avatar_ref="https://cdn.example.com/avatar.png", voice_id=_VOICE_ID,
    )
    assert result.ok, result.error
    assert runner.state["params"]["avatar_ref"]["role"] == "character"
    assert runner.state["params"]["avatar_ref"]["url"] == "https://cdn.example.com/avatar.png"


def test_save_params_default_appear_mode_stand(tmp_path, monkeypatch) -> None:
    """B3：appear_mode 默认 'stand'（planner talking_head 必填；Chat 不传不再冲突）。"""
    runner = _seed(tmp_path, monkeypatch)
    assert runner.state["params"]["appear_mode"] == "stand"

    runner2 = _seed(tmp_path, monkeypatch, session_id="dh-appear-walk", appear_mode="walk")
    assert runner2.state["params"]["appear_mode"] == "walk"

    runner3 = _runner(tmp_path, monkeypatch, session_id="dh-appear-bad")
    result = runner3.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id=_VOICE_ID, appear_mode="flying",
    )
    assert result.ok is False
    assert "appear_mode" in (result.error or "")


def test_save_params_bad_values_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params", product="玻璃杯", scene="roof", duration_sec=30,
        aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id=_VOICE_ID,
    )
    assert result.ok is False
    assert "scene" in (result.error or "")

    result = runner.run(
        "save_params", product="玻璃杯", scene="indoor", duration_sec=30,
        aspect_ratio="4:3", avatar_ref=_AVATAR, voice_id=_VOICE_ID,
    )
    assert result.ok is False
    assert "aspect_ratio" in (result.error or "")


# ============================================================================
# generate_shots — 分镜规划（复用图文 planner + 数字人口播指令）
# ============================================================================

def test_generate_shots_without_params_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("generate_shots")
    assert result.ok is False
    assert "save_params" in (result.error or "")


async def _fake_planner(params, model=None, instruction=None, session_id=None):
    return {
        "shots": [
            {"id": "1", "title": "开场钩子", "duration_sec": 10, "copy": "口播1",
             "prompt": "数字人口播提示词", "shot_type": "talking_head", "gen_mode": "t2v"},
            {"id": "2", "title": "卖点承接", "duration_sec": 10, "copy": "口播2",
             "prompt": "承接", "shot_type": "talking_head", "gen_mode": "i2v"},
            {"id": "3", "title": "CTA", "duration_sec": 10, "copy": "口播3",
             "prompt": "收束", "shot_type": "talking_head", "gen_mode": "i2v"},
        ],
        "sections": [{"key": "copy_blocks", "title": "文案区块", "fields": []}],
        "source_copy": {"full_script": "口播全文", "hook": "钩子", "cta": "CTA"},
        "meta": {"total_duration_sec": 30, "segment_sec": 10, "segment_count": 3},
        "mock": True,
    }


def test_generate_shots_lands_history(monkeypatch, tmp_path) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    result = runner.run("generate_shots")
    assert result.ok, result.error
    assert result.next_step == "rewrite_copy"
    assert len(result.data["shots"]) == 3

    detail = get_history("digital_human", runner.session_id)
    assert detail["kind"] == "digital_human"
    assert detail["shots"]
    assert detail["stage_status"]["reverse"] == "done"


def test_generate_shots_injects_digital_human_instruction(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    async def fake(params, model=None, instruction=None, session_id=None):
        captured["instruction"] = instruction
        captured["plan_params"] = params
        return await _fake_planner(params, model, instruction, session_id)

    runner = _seed(tmp_path, monkeypatch, extra_instruction="形象要年轻时尚")
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", fake)
    result = runner.run("generate_shots")
    assert result.ok, result.error
    # 数字人口播/形象锁定指令注入
    assert "数字人" in captured["instruction"]
    assert "形象一致性" in captured["instruction"]
    assert "年轻时尚" in captured["instruction"]  # extra_instruction 透传
    # 规划参数：口播形式固定 + 图文线字段
    assert captured["plan_params"]["video_form"] == "talking_head"
    assert captured["plan_params"]["product"] == "玻璃杯"
    assert captured["plan_params"]["duration_sec"] == 30
    # B1：avatar_ref 并入 refs 最前（role=character），视觉模型可看到形象图
    refs = captured["plan_params"]["refs"]
    assert refs and refs[0]["role"] == "character"
    assert refs[0]["url"] == _AVATAR["url"]


def test_generate_shots_avatar_public_url_failure_degrades(monkeypatch, tmp_path) -> None:
    """B1 降级：形象图转公网失败（mock 无 CS / data URL 上传失败）→ 跳过并入，不阻断分镜规划。"""
    captured: dict = {}

    async def fake(params, model=None, instruction=None, session_id=None):
        captured["plan_params"] = params
        return await _fake_planner(params, model, instruction, session_id)

    from fastapi import HTTPException

    def boom(ref):
        raise HTTPException(status_code=503, detail={"code": "UPSTREAM_UNAVAILABLE", "message": "mock 无 CS"})

    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", fake)
    monkeypatch.setattr("plugins.mxai.content.ref_upload.ensure_public_image_url", boom)
    result = runner.run("generate_shots")
    assert result.ok, result.error
    refs = captured["plan_params"]["refs"]
    assert not any(isinstance(r, dict) and r.get("role") == "character" for r in refs)
    # ask_user 附注形象参考暂不可用
    assert "形象参考图暂不可用" in (result.ask_user or "")


# ============================================================================
# rewrite_copy / generate_videos / check_job_status / export_capcut
# ============================================================================

def test_rewrite_copy_updates_shots(monkeypatch, tmp_path) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")

    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return {"shots": [{"copy": f"新口播-{s.get('id')}"} for s in shots], "source_copy": source_copy, "mock": True}

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy", instruction="更幽默一点")
    assert result.ok, result.error
    assert captured["instruction"] == "更幽默一点"
    assert result.data["shots"][0]["copy"] == "新口播-1"


def test_generate_videos_first_call_needs_confirmation(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")
    result = runner.run("generate_videos")
    assert result.ok
    assert result.needs_confirmation is True
    card = result.confirmation_card
    assert card and "镜" in card["description"]


def test_generate_videos_confirmed_enqueues(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")
    result = runner.run("generate_videos", confirmed=True, generate_model_pref="seedance-2.0")
    assert result.ok, result.error
    assert result.data["job_ids"]
    jobs = _load_session_jobs(runner.session_id)
    assert jobs and str(jobs[0].get("kind")) == "digital_human"


def test_generate_videos_without_shots_rejected(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    result = runner.run("generate_videos")
    assert result.ok is False
    assert "分镜" in (result.error or "")


def test_check_job_status_after_enqueue(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")
    result = runner.run("generate_videos", confirmed=True)
    assert result.ok, result.error
    status = runner.run("check_job_status")
    assert status.ok
    assert "作业" in (status.ask_user or "")


def test_export_capcut_full_flow(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    result = runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error
    assert result.data["draft_path"]

    detail = get_history("digital_human", runner.session_id)
    ss = detail["stage_status"]
    # 未合成独立 TTS（未调 synthesize_voice）→ voice 保持 skipped（模型音轨）
    assert ss["voice"] == "skipped"
    assert ss["compose"] == "done"
    legacy = detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}
    voice_mark = legacy.get("voice")
    assert voice_mark and voice_mark.get("skipped") is True
    assert "模型音轨" in (voice_mark.get("note") or "")


def test_export_capcut_without_plan_uses_heuristic(tmp_path, monkeypatch) -> None:
    """B2：Chat 链路无 compose_plan → 自动按分镜生成默认剪辑方案（不再报「缺少剪辑方案」）。"""
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")
    result = runner.run("export_capcut", drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error
    assert result.data["draft_path"]

    detail = get_history("digital_human", runner.session_id)
    legacy = detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}
    plan = (legacy.get("compose") or {}).get("compose_plan") or {}
    assert plan.get("tracks", {}).get("main_video")


# ============================================================================
# list_voices / synthesize_voice（LT-054 声音必选 + TTS 合成入片）
# ============================================================================

def test_list_voices_action_lists_mock_presets(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("list_voices")
    assert result.ok, result.error
    assert result.data["voices"]
    ids = [v["voice_id"] for v in result.data["voices"]]
    assert "sys_default_female" in ids
    assert "sys_default_male" in ids


def test_synthesize_voice_without_voice_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    # 旧会话：params 无 voice_id（模拟 LT-054 升级前的项目）
    runner._save(
        shots=[],
        params={"product": "玻璃杯", "scene": "indoor", "duration_sec": 30, "aspect_ratio": "9:16", "avatar_ref": _AVATAR},
        stage_status=runner._stage_status(done=("params",)),
        step_raw={"params": {}},
        copy_confirmed=False,
    )
    result = runner.run("synthesize_voice")
    assert result.ok is False
    assert "voice_id" in (result.error or "")


def test_synthesize_voice_merges_tts_back_to_shots(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")

    async def fake_synthesize(*, voice_id, shots, tts_model=None):
        items = []
        for i, s in enumerate(shots):
            items.append({
                "shot_id": i + 1,
                "skipped": False,
                "text": s.get("copy") or "",
                "tts_path": f"C:/tts/tts_{voice_id}_{i + 1}.mp3",
                "tts_file_id": f"tts_{voice_id}_{i + 1}.mp3",
                "tts_url": f"/content/voice-media/tts_{voice_id}_{i + 1}.mp3",
                "mock": True,
                "source": "mock_tone",
            })
        return {"voice_id": voice_id, "voice_name": "默认女声", "tts_model": "cosyvoice", "items": items, "mock": True}

    monkeypatch.setattr("plugins.mxai.content.voice_tts.synthesize_shots", fake_synthesize)
    result = runner.run("synthesize_voice", tts_model="cosyvoice")
    assert result.ok, result.error
    assert result.next_step == "export_capcut"
    assert result.data["voiced"] == 3

    detail = get_history("digital_human", runner.session_id)
    assert detail["stage_status"]["voice"] == "done"
    saved = detail.get("shots") or []
    assert saved and all(s.get("tts_url") for s in saved)
    voice_raw = (detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}).get("voice") or {}
    assert voice_raw.get("voice_id") == _VOICE_ID
    assert voice_raw.get("items")


def test_export_capcut_with_synthesized_voice_notes_tts(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("plugins.mxai.content.img_text_planner.generate_img_text_shots", _fake_planner)
    runner.run("generate_shots")

    async def fake_synthesize(*, voice_id, shots, tts_model=None):
        return {
            "voice_id": voice_id, "voice_name": "默认女声", "tts_model": "cosyvoice",
            "items": [{"shot_id": i + 1, "skipped": False, "tts_path": f"C:/tts/t{i}.mp3",
                       "tts_url": f"/content/voice-media/t{i}.mp3"} for i in range(len(shots))],
            "mock": True,
        }

    monkeypatch.setattr("plugins.mxai.content.voice_tts.synthesize_shots", fake_synthesize)
    assert runner.run("synthesize_voice").ok
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    result = runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error

    detail = get_history("digital_human", runner.session_id)
    voice_mark = (detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}).get("voice") or {}
    # 已合成 TTS → note 标记「合成入片」，不再 skipped
    assert voice_mark.get("skipped") is not True
    assert "合成入片" in (voice_mark.get("note") or "")
    assert voice_mark.get("voice_id") == _VOICE_ID


# ============================================================================
# check_project / list_history / 入口
# ============================================================================

def test_check_project_resume_after_params(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is True
    assert result.next_step == "generate_shots"


def test_check_project_no_project(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is False


def test_list_history_shows_project(tmp_path, monkeypatch) -> None:
    runner = _seed(tmp_path, monkeypatch)
    result = runner.run("list_history")
    assert result.ok
    assert result.data["items"]
    assert result.data["items"][0]["product"] == "玻璃杯"


def test_module_run_entry_dict_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = run(
        session_id="dh-entry-001", action="save_params", product="玻璃杯", scene="indoor",
        duration_sec=30, aspect_ratio="9:16", avatar_ref=_AVATAR, voice_id=_VOICE_ID,
    )
    assert out["ok"] is True
    assert out["stage"] == "reverse"
    assert out["next_step"] == "generate_shots"
    assert "ask_user" in out

    out2 = run_digital_human_video_skill(session_id="dh-entry-002", action="check_project")
    assert out2["ok"] is True
    assert out2.get("has_project") is False
