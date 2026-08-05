"""RefVideoRunner / ProductReplaceVideoRunner 全链路 mock 测试 (LT-052 M1).

覆盖：save_params 校验分支、generate_shots 落 history(kind=product_replace)、
rewrite_copy 同构/严格替换指令分支、generate_videos 确认卡与入队、
check_job_status、export_capcut、list_history、check_project 续做恢复。
"""

from __future__ import annotations

import pytest

from plugins.mxai.content.create_history import get_history, list_history
from plugins.mxai.content.create_job_queue import _load_session_jobs
from skills.mxai.product_replace_video import ProductReplaceVideoRunner, run
from skills.mxai.product_replace_video import run as run_product_replace_video_skill
from skills.mxai.viral_clone_video import ViralCloneVideoRunner, run as run_viral_clone
from skills.mxai.viral_clone_video import run as run_viral_clone_video_skill

_SOURCE = "https://cdn.example.com/seed.mp4"


def _runner(tmp_path, monkeypatch, session_id: str = "pr-session-001") -> ProductReplaceVideoRunner:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    return ProductReplaceVideoRunner(session_id=session_id)


def _seed_params(tmp_path, monkeypatch, session_id: str = "pr-session-001", **extra) -> ProductReplaceVideoRunner:
    runner = _runner(tmp_path, monkeypatch, session_id=session_id)
    result = runner.run("save_params", source_video=_SOURCE, **extra)
    assert result.ok, result.error
    return runner


# ============================================================================
# save_params 校验分支
# ============================================================================

def test_save_params_missing_source_video_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("save_params", new_script="新口播")
    assert result.ok is False
    assert "source_video" in (result.error or "")


def test_save_params_defaults_applied(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch, new_script="新口播文案")
    params = runner.state["params"]
    assert params["source_video"] == _SOURCE
    assert params["segment_sec"] == 13
    assert params["aspect_ratio"] == "9:16"
    assert params["max_shots"] == 6
    assert params["new_script"] == "新口播文案"
    # history 已落盘（kind=product_replace），七段 stage_status
    detail = get_history("product_replace", runner.session_id)
    ss = detail["stage_status"]
    assert set(ss) == {"params", "reverse", "copy_rewrite", "shot_edit", "generate", "voice", "compose"}
    assert ss["params"] == "done"
    assert ss["voice"] == "pending"


def test_save_params_bad_values_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("save_params", source_video=_SOURCE, segment_sec=100)
    assert result.ok is False
    assert "segment_sec" in (result.error or "")

    result = runner.run("save_params", source_video=_SOURCE, aspect_ratio="4:3")
    assert result.ok is False
    assert "aspect_ratio" in (result.error or "")

    result = runner.run("save_params", source_video=_SOURCE, new_script="x" * 4001)
    assert result.ok is False
    assert "new_script" in (result.error or "")


# ============================================================================
# generate_shots — 反推落 history，kind=product_replace
# ============================================================================

def test_generate_shots_without_params_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run("generate_shots")
    assert result.ok is False
    assert "save_params" in (result.error or "")


def test_generate_shots_reverse_lands_history(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    result = runner.run("generate_shots")
    assert result.ok, result.error
    assert result.next_step == "rewrite_copy"
    assert result.data["shots"]

    detail = get_history("product_replace", runner.session_id)
    assert detail["kind"] == "product_replace"
    assert detail["shots"]
    assert detail["params"]["source_video"] == _SOURCE
    assert detail["stage_status"]["reverse"] == "done"
    assert detail["source_url"] == _SOURCE


# ============================================================================
# rewrite_copy — 指令分支（严格替换 / 同构改写）
# ============================================================================

def _fake_rewrite(source_copy, shots, instruction=None, session_id=None):
    return {
        "shots": [{"copy": f"改写-{s.get('id')}"} for s in shots],
        "source_copy": {"full_script": "改写后全文", "hook": "新钩子"},
        "instruction": instruction,
        "mock": True,
    }


def test_rewrite_copy_new_script_strict_replace(monkeypatch, tmp_path) -> None:
    runner = _seed_params(tmp_path, monkeypatch, new_script="全新口播：一杯搞定")
    runner.run("generate_shots")
    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return _fake_rewrite(source_copy, shots, instruction, session_id)

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy")
    assert result.ok, result.error
    assert captured["instruction"]
    assert "全新口播：一杯搞定" in captured["instruction"]
    assert "对齐原片时间轴" in captured["instruction"]


def test_rewrite_copy_no_script_isomorphism(monkeypatch, tmp_path) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return _fake_rewrite(source_copy, shots, instruction, session_id)

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy")
    assert result.ok, result.error
    assert captured["instruction"]
    assert "同构替换改写" in captured["instruction"]  # 多路同构替换改写（M1.05 措辞）
    assert "钩子" in captured["instruction"]
    assert "CTA" in captured["instruction"]


# ============================================================================
# generate_videos — 危险操作确认 + 入队
# ============================================================================

def test_generate_videos_first_call_needs_confirmation(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    result = runner.run("generate_videos")
    assert result.ok
    assert result.needs_confirmation is True
    card = result.confirmation_card
    assert card and card["title"] == "开始生成视频"
    assert "镜" in card["description"]
    assert "耗时" in card["description"]
    assert "算力" in card["description"]
    # 未确认不得入队
    assert _load_session_jobs(runner.session_id) == []


def test_generate_videos_confirmed_enqueues(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    shots_result = runner.run("generate_shots")
    n_shots = len(shots_result.data["shots"])

    result = runner.run("generate_videos", confirmed=True)
    assert result.ok, result.error
    assert result.data["job_count"] == n_shots
    jobs = _load_session_jobs(runner.session_id)
    assert len(jobs) == n_shots
    assert all(j["kind"] == "product_replace" for j in jobs)
    assert all(j["job_type"] == "generate" for j in jobs)


def test_generate_videos_without_shots_rejected(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    result = runner.run("generate_videos", confirmed=True)
    assert result.ok is False
    assert "分镜" in (result.error or "")


# ============================================================================
# check_job_status / list_history
# ============================================================================

def test_check_job_status_after_enqueue(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    enqueued = runner.run("generate_videos", confirmed=True)
    job_id = enqueued.data["job_ids"][0]

    result = runner.run("check_job_status", job_id=job_id)
    assert result.ok
    assert result.data["target"]["job_id"] == job_id

    result = runner.run("check_job_status")
    assert result.ok
    assert len(result.data["jobs"]) >= 1


def test_list_history_shows_project(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    result = runner.run("list_history")
    assert result.ok
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["session_id"] == runner.session_id

    # 直接调用 content 层 list_history(kind=product_replace) 亦可
    resp = list_history("product_replace", limit=20)
    assert resp["total"] == 1


# ============================================================================
# export_capcut — 导出 + voice 默认跳过独立 TTS
# ============================================================================

def test_export_capcut_full_flow(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    result = runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error
    assert result.data["draft_path"]

    detail = get_history("product_replace", runner.session_id)
    ss = detail["stage_status"]
    # voice 段默认跳过独立 TTS（使用模型音轨）：checkpoint 读侧标 skipped 并保留说明
    assert ss["voice"] == "skipped"
    assert ss["compose"] == "done"
    assert detail["copy_confirmed"] is True
    legacy = detail.get("step_raw") if isinstance(detail.get("step_raw"), dict) else {}
    voice_mark = legacy.get("voice")
    assert voice_mark and voice_mark.get("skipped") is True
    assert "跳过独立 TTS" in (voice_mark.get("note") or "")


def test_export_capcut_missing_plan_rejected(tmp_path, monkeypatch) -> None:
    runner = _seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    result = runner.run("export_capcut", compose_plan={})
    assert result.ok is False
    assert "compose_plan" in (result.error or "")


# ============================================================================
# check_project — 续做恢复
# ============================================================================

def test_check_project_resume_after_params(tmp_path, monkeypatch) -> None:
    _seed_params(tmp_path, monkeypatch, session_id="resume-001")
    # 新实例（模拟重启）恢复同一会话
    runner = ProductReplaceVideoRunner(session_id="resume-001")
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is True
    assert result.data["params"]["source_video"] == _SOURCE
    assert result.next_step == "generate_shots"
    assert "已完成" in (result.ask_user or "")


def test_check_project_resume_after_reverse(tmp_path, monkeypatch) -> None:
    _seed_params(tmp_path, monkeypatch, session_id="resume-002")
    runner = ProductReplaceVideoRunner(session_id="resume-002")
    runner.run("generate_shots")
    fresh = ProductReplaceVideoRunner(session_id="resume-002")
    result = fresh.run("check_project")
    assert result.ok
    assert result.next_step == "rewrite_copy"
    assert result.data["shots"]


def test_check_project_no_project(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch, session_id="fresh-000")
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is False
    assert result.next_step == "save_params"


# ============================================================================
# 统一入口（module-level run / runner 兼容层）
# ============================================================================

def test_module_run_entry_dict_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = run(session_id="entry-001", action="save_params", source_video=_SOURCE)
    assert out["ok"] is True
    assert out["stage"] == "reverse"
    assert out["next_step"] == "generate_shots"
    assert "ask_user" in out
    assert "session_id" in out

    # runner 兼容层 re-export
    out2 = run_product_replace_video_skill(session_id="entry-002", action="check_project")
    assert out2["ok"] is True
    assert out2.get("has_project") is False


# ============================================================================
# 多路替换（M1.05 矫正）— refs.role 校验 / replace_tracks 推导 / 改写指令分支 / 反推声明
# ============================================================================

def test_save_params_refs_invalid_role_rejected(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    result = runner.run(
        "save_params",
        source_video=_SOURCE,
        refs=[{"id": "r1", "url": "https://cdn.example.com/p.png", "role": "avatar"}],
    )
    assert result.ok is False
    assert "role" in (result.error or "")


def test_save_params_replace_tracks_derived(tmp_path, monkeypatch) -> None:
    # 单路：仅产品
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-tracks-1",
        refs=[{"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"}],
    )
    assert runner.state["params"]["replace_tracks"] == ["product"]

    # 双路：产品 + 人物（按规范角色序 character/product/scene/style）
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-tracks-2",
        refs=[
            {"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"},
            {"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character"},
        ],
    )
    assert runner.state["params"]["replace_tracks"] == ["character", "product"]

    # enabled=False 的参考图不计入替换路
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-tracks-3",
        refs=[
            {"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character", "enabled": False},
            {"id": "s1", "url": "https://cdn.example.com/s.png", "role": "scene"},
        ],
    )
    assert runner.state["params"]["replace_tracks"] == ["scene"]

    # 无 refs → 无替换路（纯框架锁定）
    runner = _seed_params(tmp_path, monkeypatch, session_id="pr-tracks-4")
    assert runner.state["params"]["replace_tracks"] == []


def test_rewrite_copy_isomorphism_branches_by_tracks(monkeypatch, tmp_path) -> None:
    # 双路（产品+人物）：指令含两路要点，场景/风格走保留
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-branch-1",
        refs=[
            {"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"},
            {"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character"},
        ],
    )
    runner.run("generate_shots")
    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return _fake_rewrite(source_copy, shots, instruction, session_id)

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy")
    assert result.ok, result.error
    instr = captured["instruction"]
    assert "产品路" in instr
    assert "人物路" in instr
    assert "未提供参考图的路" in instr  # 场景/风格保留

    # 单路（仅人物）：含人物路，产品路不进主动替换要点
    captured.clear()
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-branch-2",
        refs=[{"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character"}],
    )
    runner.run("generate_shots")
    runner.run("rewrite_copy")
    instr = captured["instruction"]
    assert "人物路" in instr
    assert "产品路" not in instr
    assert "保留原片对应要素" in instr

    # 无 refs：纯框架锁定
    captured.clear()
    runner = _seed_params(tmp_path, monkeypatch, session_id="pr-branch-3")
    runner.run("generate_shots")
    runner.run("rewrite_copy")
    assert "仅框架锁定" in captured["instruction"]


def test_reverse_kwargs_carries_track_declaration(tmp_path, monkeypatch) -> None:
    runner = _seed_params(
        tmp_path, monkeypatch, session_id="pr-rev-1",
        refs=[
            {"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"},
            {"id": "c1", "url": "https://cdn.example.com/c.png", "role": "character"},
        ],
        extra_instruction="新产品是咖啡杯",
    )
    kwargs = runner._reverse_kwargs(runner.state["params"])
    assert "多路替换" in kwargs["instruction"]
    assert "产品" in kwargs["instruction"]
    assert "人物" in kwargs["instruction"]
    assert "新产品是咖啡杯" in kwargs["instruction"]  # extra_instruction 保留
    assert kwargs["kind"] == "product_replace"

    # 无替换路 → instruction 仅 extra_instruction（此处为空 → None）
    runner2 = _seed_params(tmp_path, monkeypatch, session_id="pr-rev-2")
    kwargs2 = runner2._reverse_kwargs(runner2.state["params"])
    assert kwargs2["instruction"] is None


def test_save_params_params_saved_mentions_tracks(tmp_path, monkeypatch) -> None:
    runner = _runner(tmp_path, monkeypatch, session_id="pr-ask-1")
    result = runner.run(
        "save_params",
        source_video=_SOURCE,
        refs=[{"id": "p1", "url": "https://cdn.example.com/p.png", "role": "product"}],
    )
    assert result.ok
    assert "替换路：产品" in (result.ask_user or "")

    runner = _runner(tmp_path, monkeypatch, session_id="pr-ask-2")
    result = runner.run("save_params", source_video=_SOURCE)
    assert result.ok
    assert "要替换哪些路" in (result.ask_user or "")


# ============================================================================
# ViralCloneVideoRunner 全链路 mock 测试 (LT-052 M2)
# ============================================================================


def _v_runner(tmp_path, monkeypatch, session_id: str = "vc-session-001") -> ViralCloneVideoRunner:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    return ViralCloneVideoRunner(session_id=session_id)


def _v_seed_params(tmp_path, monkeypatch, session_id: str = "vc-session-001", **extra) -> ViralCloneVideoRunner:
    runner = _v_runner(tmp_path, monkeypatch, session_id=session_id)
    result = runner.run("save_params", source_video=_SOURCE, **extra)
    assert result.ok, result.error
    return runner


# --- save_params 校验（仅 source_video 必填；无产品替换参数） ---

def test_viral_save_params_missing_source_video_rejected(tmp_path, monkeypatch) -> None:
    runner = _v_runner(tmp_path, monkeypatch)
    result = runner.run("save_params", max_shots=8)
    assert result.ok is False
    assert "source_video" in (result.error or "")


def test_viral_save_params_defaults_applied(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    params = runner.state["params"]
    assert params["source_video"] == _SOURCE
    assert params["max_shots"] == 6
    # 仿爆款无 segment_sec / aspect_ratio / new_script 参数
    assert "segment_sec" not in params
    assert "aspect_ratio" not in params
    assert "new_script" not in params
    # history 已落盘（kind=viral_clone），七段 stage_status
    detail = get_history("viral_clone", runner.session_id)
    ss = detail["stage_status"]
    assert set(ss) == {"params", "reverse", "copy_rewrite", "shot_edit", "generate", "voice", "compose"}
    assert ss["params"] == "done"
    assert ss["voice"] == "pending"


def test_viral_save_params_bad_values_rejected(tmp_path, monkeypatch) -> None:
    runner = _v_runner(tmp_path, monkeypatch)
    result = runner.run("save_params", source_video=_SOURCE, max_shots=100)
    assert result.ok is False
    assert "max_shots" in (result.error or "")

    result = runner.run("save_params", source_video=_SOURCE, max_shots=0)
    assert result.ok is False
    assert "max_shots" in (result.error or "")

    result = runner.run("save_params", source_video=_SOURCE, instruction="x" * 2001)
    assert result.ok is False
    assert "instruction" in (result.error or "")


def test_viral_save_params_optional_fields(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(
        tmp_path,
        monkeypatch,
        max_shots=4,
        instruction="强调产品卖点，节奏加快",
        refs=[{"id": "r1", "url": "https://cdn.example.com/ref.jpg", "role": "character", "enabled": True}],
    )
    params = runner.state["params"]
    assert params["max_shots"] == 4
    assert params["instruction"] == "强调产品卖点，节奏加快"
    assert params["refs"][0]["role"] == "character"


# --- generate_shots — 反推落 history，kind=viral_clone ---

def test_viral_generate_shots_without_params_rejected(tmp_path, monkeypatch) -> None:
    runner = _v_runner(tmp_path, monkeypatch)
    result = runner.run("generate_shots")
    assert result.ok is False
    assert "save_params" in (result.error or "")


def test_viral_generate_shots_reverse_lands_history(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch, instruction="锁定人物 DNA")
    result = runner.run("generate_shots")
    assert result.ok, result.error
    assert result.next_step == "rewrite_copy"
    assert result.data["shots"]
    assert result.data["source_copy"]

    detail = get_history("viral_clone", runner.session_id)
    assert detail["kind"] == "viral_clone"
    assert detail["shots"]
    assert detail["params"]["source_video"] == _SOURCE
    assert detail["stage_status"]["reverse"] == "done"
    assert detail["source_url"] == _SOURCE


# --- rewrite_copy — 默认保留原口播 / instruction 透传 ---

def test_viral_rewrite_copy_default_keep_or_rewrite(monkeypatch, tmp_path) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return {
            "shots": [{"copy": f"原样-{s.get('id')}"} for s in shots],
            "source_copy": {"full_script": "原口播", "hook": "钩子"},
            "instruction": instruction,
            "mock": True,
        }

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy")
    assert result.ok, result.error
    assert captured["instruction"]
    assert "保留原口播" in captured["instruction"]
    assert "按用户要求改写" in captured["instruction"]


def test_viral_rewrite_copy_instruction_passthrough(monkeypatch, tmp_path) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    captured: dict = {}

    def fake(source_copy, shots, instruction=None, session_id=None):
        captured["instruction"] = instruction
        return {
            "shots": [{"copy": f"改写-{s.get('id')}"} for s in shots],
            "source_copy": {"full_script": "改写后全文", "hook": "新钩子"},
            "instruction": instruction,
            "mock": True,
        }

    monkeypatch.setattr("plugins.mxai.content.copy_rewrite.rewrite_viral_copy", fake)
    result = runner.run("rewrite_copy", instruction="换成更幽默的语气，保留节奏")
    assert result.ok, result.error
    assert captured["instruction"] == "换成更幽默的语气，保留节奏"


# --- generate_videos — 危险操作确认 + 入队 kind=viral_clone ---

def test_viral_generate_videos_first_call_needs_confirmation(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    result = runner.run("generate_videos")
    assert result.ok
    assert result.needs_confirmation is True
    card = result.confirmation_card
    assert card and card["title"] == "开始生成视频"
    assert "镜" in card["description"]
    assert "耗时" in card["description"]
    assert "算力" in card["description"]
    # 未确认不得入队
    assert _load_session_jobs(runner.session_id) == []


def test_viral_generate_videos_confirmed_enqueues(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    shots_result = runner.run("generate_shots")
    n_shots = len(shots_result.data["shots"])

    result = runner.run("generate_videos", confirmed=True)
    assert result.ok, result.error
    assert result.data["job_count"] == n_shots
    jobs = _load_session_jobs(runner.session_id)
    assert len(jobs) == n_shots
    assert all(j["kind"] == "viral_clone" for j in jobs)
    assert all(j["job_type"] == "generate" for j in jobs)


def test_viral_generate_videos_without_shots_rejected(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    result = runner.run("generate_videos", confirmed=True)
    assert result.ok is False
    assert "分镜" in (result.error or "")


# --- check_job_status / list_history ---

def test_viral_check_job_status_after_enqueue(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    enqueued = runner.run("generate_videos", confirmed=True)
    job_id = enqueued.data["job_ids"][0]

    result = runner.run("check_job_status", job_id=job_id)
    assert result.ok
    assert result.data["target"]["job_id"] == job_id

    result = runner.run("check_job_status")
    assert result.ok
    assert len(result.data["jobs"]) >= 1


def test_viral_list_history_shows_project(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    result = runner.run("list_history")
    assert result.ok
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["session_id"] == runner.session_id

    # 直接调用 content 层 list_history(kind=viral_clone) 亦可
    resp = list_history("viral_clone", limit=20)
    assert resp["total"] == 1


# --- export_capcut — 导出 + voice 默认跳过独立 TTS ---

def test_viral_export_capcut_full_flow(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    from plugins.mxai.content.compose_plan import build_heuristic_plan

    plan = build_heuristic_plan(runner.state["shots"])
    result = runner.run("export_capcut", compose_plan=plan, drafts_dir=str(tmp_path / "drafts"))
    assert result.ok, result.error
    assert result.data["draft_path"]

    detail = get_history("viral_clone", runner.session_id)
    ss = detail["stage_status"]
    # voice 段默认跳过独立 TTS（使用模型音轨）：checkpoint 读侧标 skipped 并保留说明
    assert ss["voice"] == "skipped"
    assert ss["compose"] == "done"
    assert detail["copy_confirmed"] is True


def test_viral_export_capcut_missing_plan_rejected(tmp_path, monkeypatch) -> None:
    runner = _v_seed_params(tmp_path, monkeypatch)
    runner.run("generate_shots")
    result = runner.run("export_capcut", compose_plan={})
    assert result.ok is False
    assert "compose_plan" in (result.error or "")


# --- check_project — 续做恢复 ---

def test_viral_check_project_resume_after_params(tmp_path, monkeypatch) -> None:
    _v_seed_params(tmp_path, monkeypatch, session_id="vc-resume-001")
    # 新实例（模拟重启）恢复同一会话
    runner = ViralCloneVideoRunner(session_id="vc-resume-001")
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is True
    assert result.data["params"]["source_video"] == _SOURCE
    assert result.next_step == "generate_shots"
    assert "已完成" in (result.ask_user or "")


def test_viral_check_project_resume_after_reverse(tmp_path, monkeypatch) -> None:
    _v_seed_params(tmp_path, monkeypatch, session_id="vc-resume-002")
    runner = ViralCloneVideoRunner(session_id="vc-resume-002")
    runner.run("generate_shots")
    fresh = ViralCloneVideoRunner(session_id="vc-resume-002")
    result = fresh.run("check_project")
    assert result.ok
    assert result.next_step == "rewrite_copy"
    assert result.data["shots"]


def test_viral_check_project_no_project(tmp_path, monkeypatch) -> None:
    runner = _v_runner(tmp_path, monkeypatch, session_id="vc-fresh-000")
    result = runner.run("check_project")
    assert result.ok
    assert result.data["has_project"] is False
    assert result.next_step == "save_params"


# --- 统一入口（module-level run / runner 兼容层） ---

def test_viral_module_run_entry_dict_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = run_viral_clone(session_id="vc-entry-001", action="save_params", source_video=_SOURCE)
    assert out["ok"] is True
    assert out["stage"] == "reverse"
    assert out["next_step"] == "generate_shots"
    assert "ask_user" in out
    assert "session_id" in out

    # runner 兼容层 re-export
    out2 = run_viral_clone_video_skill(session_id="vc-entry-002", action="check_project")
    assert out2["ok"] is True
    assert out2.get("has_project") is False
