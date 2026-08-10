"""OpenMontage 作为 Hermes 插件的契约测试。

覆盖三件在合并后最容易悄悄坏掉的事：

1. **插件能被大脑装上** —— 工具、技能、钩子都注册到位，名字与 plugin.yaml 一致。
2. **三个根解析正确** —— 代码根在插件内、仓库根靠标志物找到、数据根可被宿主重定向。
   这条最隐蔽：路径错了不会报错，只会读到空目录然后"什么都没找到"。
3. **治理钩子真的拦得住** —— 硬规则从文档变成运行时拦截，就必须有违规对照。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import plugins.openmontage as om
from plugins.openmontage.bridge import handle_catalog, handle_pipeline, handle_project
from plugins.openmontage.governance import pre_tool_call
from plugins.openmontage.lib.paths import (
    CODE_ROOT,
    DATA_ROOT,
    PIPELINE_DEFS_DIR,
    REPO_ROOT,
    SKILLS_DIR,
)


class _RecordingCtx:
    """记录插件注册了什么，不真的挂进宿主。"""

    def __init__(self) -> None:
        self.tools: list[str] = []
        self.skills: list[str] = []
        self.skill_paths: list[Path] = []
        self.hooks: list[str] = []
        self.middleware: list[str] = []
        self.routes: list[tuple[str, object]] = []

    def register_tool(self, name, **_kw):  # noqa: ANN001
        self.tools.append(name)

    def register_skill(self, name, path, description=""):  # noqa: ANN001
        assert Path(path).is_file(), f"技能文件不存在: {path}"
        self.skills.append(name)
        self.skill_paths.append(Path(path))

    def register_hook(self, hook_name, callback):  # noqa: ANN001
        assert callable(callback)
        self.hooks.append(hook_name)

    def register_middleware(self, kind, callback):  # noqa: ANN001
        assert callable(callback)
        self.middleware.append(kind)

    def register_routes(self, router, *, prefix="", tags=None):  # noqa: ANN001
        self.routes.append((prefix, router))


@pytest.fixture(scope="module")
def registered() -> _RecordingCtx:
    ctx = _RecordingCtx()
    om.register(ctx)
    return ctx


# ─── 1. 插件装载契约 ──────────────────────────────────────────────────


def test_manifest_matches_registered_tools(registered):
    """plugin.yaml 声明的工具必须与实际注册的一致。

    两者漂移时 Hermes 的工具目录会跟真实能力对不上 —— 大脑要么以为有个
    不存在的工具，要么看不见一个已经能用的工具。
    """
    manifest = yaml.safe_load((CODE_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "openmontage"
    assert sorted(manifest["provides_tools"]) == sorted(registered.tools)


def test_registers_governance_hooks(registered):
    assert "pre_tool_call" in registered.hooks
    assert "post_tool_call" in registered.hooks
    assert "pre_llm_call" in registered.hooks
    assert "llm_request" in registered.middleware


def test_session_brief_extracts_from_agent_guide():
    """session-brief 标记是送达通道的唯一真源；删掉会让按需注入静默失效。"""
    from plugins.openmontage.skills import load_session_brief, pre_llm_call

    brief = load_session_brief()
    assert brief, "AGENT_GUIDE.md 缺少 om:session-brief 标记块"
    assert "om_preflight" in brief
    assert 'skill_view("openmontage:agent-guide")' in brief
    assert "om_director" in brief
    assert "不是 Hermes 全局" in brief or "插件" in brief

    # 无意图（问候）→ 不注入
    assert pre_llm_call(is_first_turn=True, user_message="hi") is None
    assert pre_llm_call(is_first_turn=True, user_message="你好") is None
    assert pre_llm_call() is None

    # 有 OM/视频意图 → 注入
    hit = pre_llm_call(
        is_first_turn=True,
        user_message="帮我做一个短视频",
        session_id="test-brief-intent-1",
    )
    assert isinstance(hit, dict) and hit.get("context") == brief
    # 同一会话只注入一次
    assert (
        pre_llm_call(
            user_message="继续做这个视频项目",
            session_id="test-brief-intent-1",
        )
        is None
    )


def test_pre_llm_call_skips_brief_in_headless_stage(monkeypatch):
    """无头阶段 agent 不得注入编排大脑的 om_run/om_job 轮询简报。"""
    from plugins.openmontage.skills import pre_llm_call

    monkeypatch.setenv("OPENMONTAGE_HEADLESS_STAGE", "1")
    assert (
        pre_llm_call(is_first_turn=True, user_message="帮我做一个短视频") is None
    )


def test_message_looks_like_openmontage_intent():
    from plugins.openmontage.skills import message_looks_like_openmontage_intent as looks

    assert looks("hi") is False
    assert looks("Hello!") is False
    assert looks("你好") is False
    assert looks("在吗") is False
    assert looks("帮我做一个短视频") is True
    assert looks("查一下 my-copy-01 的 om_project") is True
    assert looks("continue research pipeline") is True


def test_filter_stage_toolsets_drops_openmontage():
    """无头阶段：openmontage_stage + web + skills_view；永不含编排 openmontage。"""
    from plugins.openmontage.backlot.agent_executor import (
        _HEADLESS_STAGE_TOOLSET_ORDER,
        _filter_stage_toolsets,
        _resolve_stage_toolsets,
    )
    from plugins.openmontage.bridge import TOOLSET
    from plugins.openmontage.stage_tools import TOOLSET as STAGE_TOOLSET

    filtered = _filter_stage_toolsets(["terminal", TOOLSET, "file", "browser", "web"])
    assert TOOLSET not in filtered
    assert filtered == list(_HEADLESS_STAGE_TOOLSET_ORDER)
    assert STAGE_TOOLSET in filtered
    assert "web" in filtered
    assert "file" not in filtered
    assert "terminal" not in filtered
    assert "code_execution" not in filtered
    assert "browser" not in filtered

    # 固定面，不依赖平台交集
    assert _resolve_stage_toolsets(["skills"]) == list(_HEADLESS_STAGE_TOOLSET_ORDER)
    assert _resolve_stage_toolsets([TOOLSET, "browser"]) == list(
        _HEADLESS_STAGE_TOOLSET_ORDER
    )
    assert TOOLSET not in _resolve_stage_toolsets(None)
    assert "web" in _HEADLESS_STAGE_TOOLSET_ORDER


def test_registers_backlot_routes(registered):
    prefixes = [p for p, _ in registered.routes]
    assert "/api/plugins/openmontage" in prefixes
    assert "/plugins/openmontage" in prefixes
    assert "" in prefixes  # /thumb + /media root compat
    assert prefixes.count("/api/plugins/openmontage") == 2  # api + media


def test_registers_agent_guide_and_meta_skills(registered):
    assert "agent-guide" in registered.skills
    # meta 技能是跨阶段方法论，应常驻；阶段导演技能走 om_director 动态供给。
    assert "reviewer" in registered.skills
    assert "checkpoint-protocol" in registered.skills
    # 按来源目录判定而非名字后缀：voice-performance-director 是跨阶段的
    # meta 技能，该常驻；skills/pipelines/ 下的才是阶段导演，走 om_director。
    staged = [p for p in registered.skill_paths if "pipelines" in p.parts]
    assert not staged, (
        f"阶段导演技能不该常驻技能索引（十几条流水线乘以七八个阶段会淹没大脑）: {staged}"
    )


# ─── 2. 三个根 ───────────────────────────────────────────────────────


def test_code_root_holds_the_shipped_assets():
    """随代码分发的东西都在代码根下。"""
    assert (CODE_ROOT / "AGENT_GUIDE.md").is_file()
    assert SKILLS_DIR.is_dir()
    assert PIPELINE_DEFS_DIR.is_dir()
    assert CODE_ROOT.name == "openmontage"


def test_repo_root_found_by_marker_not_by_depth():
    """仓库根靠标志物向上探测，且确实在代码根之上。"""
    assert REPO_ROOT != CODE_ROOT, "插件形态下两根必须分开"
    assert CODE_ROOT.is_relative_to(REPO_ROOT)
    assert any(
        (REPO_ROOT / m).exists() for m in (".git", "vendor", "remotion-composer")
    ), "REPO_ROOT 应落在带仓库标志物的目录上"


def test_data_root_is_redirectable(tmp_path):
    """宿主注入 OPENMONTAGE_DATA_ROOT 后整个数据面平移，且目录名不变。

    起子进程而不是 ``importlib.reload``：路径常量是模块级的，重载会让
    已经 ``from ... import PROJECTS_DIR`` 的模块与新值不一致，
    污染同一次 pytest 运行里的其它用例。
    """
    import os
    import subprocess
    import sys

    montage = tmp_path / "montage"
    # 清掉继承来的 OPENMONTAGE_* 覆盖：backlot_screenshot_stage 在 import 时就会
    # 设 OPENMONTAGE_PROJECTS_DIR，全量跑时它已经在进程环境里了，
    # 会盖掉本用例要验证的数据根推导。
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("OPENMONTAGE_")
    }
    env.update(
        {
            "OPENMONTAGE_DATA_ROOT": str(montage),
            "PYTHONPATH": str(CODE_ROOT.parent.parent),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    probe = (
        "import json;"
        "from plugins.openmontage.lib import paths as p;"
        "print(json.dumps({"
        "'data': str(p.DATA_ROOT),"
        "'projects': str(p.PROJECTS_DIR),"
        "'backlot': str(p.BACKLOT_STATE_DIR),"
        "'music': str(p.MUSIC_LIBRARY_DIR),"
        "'composer': str(p.COMPOSER_DIR),"
        "'skills': str(p.SKILLS_DIR),"
        "'code': str(p.CODE_ROOT)}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)

    assert Path(got["data"]) == montage
    # montage/ 下的布局与仓库根逐字一致 —— 目录不改名是这次迁移的前提
    assert Path(got["projects"]) == montage / "projects"
    assert Path(got["backlot"]) == montage / ".backlot"
    assert Path(got["music"]) == montage / "music_library"
    assert Path(got["composer"]) == montage / "remotion-composer"
    # 代码根不受数据根影响
    assert Path(got["skills"]) == Path(got["code"]) / "skills"


def _probe_data_root(tmp_path, *, script: str, env_extra: dict) -> dict:
    """在子进程里取一次路径常量。

    常量是模块级的，``importlib.reload`` 会让已经 ``from ... import`` 过的模块
    与新值不一致，污染同一次 pytest 运行里的其它用例。
    """
    import os
    import subprocess
    import sys

    probe = tmp_path / "probe_paths.py"
    probe.write_text(script, encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENMONTAGE_")}
    env.pop("HUB_DATA_DIR", None)
    env.update(env_extra)
    env["PYTHONPATH"] = str(CODE_ROOT.parent.parent)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        [sys.executable, str(probe)], env=env, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


_DUMP = (
    "import json\n"
    "from plugins.openmontage.lib import paths as p\n"
    "print(json.dumps({'data': str(p.DATA_ROOT), 'repo': str(p.REPO_ROOT)}))\n"
)


def test_data_root_follows_the_profile_when_hosted(tmp_path):
    """挂在 Hermes 下时数据面落在 profile 目录，而不是跟源码混在仓库根。"""
    from hermes_constants import get_hermes_home

    got = _probe_data_root(tmp_path, script=_DUMP, env_extra={})
    assert Path(got["data"]) == get_hermes_home() / "montage"


def test_data_root_agrees_between_hub_and_cli(tmp_path):
    """hub 拉起的进程带 HUB_DATA_DIR，CLI 起的不带 —— 两者必须解析到同一份数据。

    曾经这里读的是 ``HUB_DATA_DIR`` 环境变量，于是同一台机器上 hub 看到 5 个
    项目、CLI 看到 0 个。
    """
    from hermes_constants import get_hermes_home

    hosted = _probe_data_root(
        tmp_path, script=_DUMP, env_extra={"HUB_DATA_DIR": str(get_hermes_home())}
    )
    cli = _probe_data_root(tmp_path, script=_DUMP, env_extra={})
    assert hosted["data"] == cli["data"]


def test_data_root_falls_back_to_repo_root_standalone(tmp_path):
    """独立签出里没有宿主可问，退回仓库根 —— 迁移前的老行为。"""
    script = (
        "import sys\n"
        # 置 None 让后续 import 抛 ImportError，等价于宿主不存在。
        "sys.modules['hermes_constants'] = None\n"
    ) + _DUMP
    got = _probe_data_root(tmp_path, script=script, env_extra={})
    assert Path(got["data"]) == Path(got["repo"])


# ─── 3. 只读面对真实数据可用 ──────────────────────────────────────────


def test_pipeline_tool_lists_real_manifests():
    payload = json.loads(handle_pipeline({}))
    assert payload["ok"]
    assert "framework-smoke" in payload["pipelines"]


def test_pipeline_tool_resolves_stage_skills():
    payload = json.loads(handle_pipeline({"name": "reference-driven"}))
    assert payload["ok"]
    stages = payload["stages"]
    assert stages, "reference-driven 应有阶段"
    resolved = [s for s in stages if s["director_skill"]]
    assert resolved, "至少要有阶段能解析出导演技能"
    for stage in resolved:
        assert (CODE_ROOT / stage["director_skill"]).is_file(), (
            f"{stage['name']} 的技能解析到了不存在的文件: {stage['director_skill']}"
        )


def test_catalog_tool_reports_discovered_tools():
    """工具发现要用插件内的包名，不能撞上 agent-hub 自己的 tools 包。"""
    payload = json.loads(handle_catalog({}))
    assert payload["ok"]
    assert payload["tool_count"] > 50, (
        f"只发现 {payload['tool_count']} 个工具——包名很可能解析到了 agent-hub 的 src/tools/"
    )


def test_project_tool_lists_projects():
    payload = json.loads(handle_project({}))
    assert payload["ok"]
    assert isinstance(payload["projects"], list)


def test_unknown_pipeline_reports_alternatives():
    """报错要能自救：告诉调用方有哪些可选，而不是只说一句失败。"""
    payload = json.loads(handle_pipeline({"name": "__nope__"}))
    assert payload["ok"] is False
    assert payload["available"]


# ─── 4. 治理拦截（含违规对照）────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "python scripts/rerun_my_copy_01.py",
        "python scripts/advance_koubo_test.py --stage compose",
    ],
)
def test_blocks_pipeline_bypass_scripts(command):
    verdict = pre_tool_call(
        tool_name="terminal",
        args={"label": "跑脚本", "command": command},
    )
    assert verdict is not None, f"Rule Zero 应拦下绕流水线的脚本: {command}"
    assert verdict["action"] == "block"
    assert "Rule Zero" in verdict["message"]


@pytest.mark.parametrize(
    "command",
    ["ls projects/", "git status", "python -m plugins.openmontage.lib.project_status x"],
)
def test_allows_ordinary_commands(command):
    """对照组：正常命令必须放行，否则治理就成了瘫痪。"""
    assert (
        pre_tool_call(
            tool_name="terminal",
            args={"label": "检查环境", "command": command},
        )
        is None
    )


@pytest.mark.parametrize(
    "code",
    [
        "from plugins.openmontage.backlot import stage_runner\nstage_runner.prepare_stage_run(...)",
        "import plugins.openmontage.backlot.stage_runner as sr\nsr.schedule_run_task(t)",
    ],
)
def test_blocks_execute_code_pipeline_imports(code):
    verdict = pre_tool_call(
        tool_name="execute_code",
        args={"label": "探测 stage_runner", "code": code},
    )
    assert verdict is not None
    assert verdict["action"] == "block"
    assert "om_run" in verdict["message"]


def test_allows_innocent_execute_code():
    assert (
        pre_tool_call(
            tool_name="execute_code",
            args={"label": "算一加一", "code": "print(1+1)"},
        )
        is None
    )


@pytest.mark.parametrize("tool_name", ["execute_code", "terminal", "om_job"])
def test_blocks_missing_invocation_label(tool_name):
    args = {
        "execute_code": {"code": "print(1)"},
        "terminal": {"command": "ls"},
        "om_job": {"project_id": "demo", "task_id": "abc"},
    }[tool_name]
    verdict = pre_tool_call(tool_name=tool_name, args=args)
    assert verdict is not None
    assert verdict["action"] == "block"
    assert "label" in verdict["message"].lower()


def test_blocks_blank_invocation_label():
    verdict = pre_tool_call(
        tool_name="execute_code",
        args={"label": "   ", "code": "print(1)"},
    )
    assert verdict is not None and verdict["action"] == "block"


def test_allows_read_file_project_artifact():
    """项目 artifacts 产物内容仍可 read_file（进度本身走 om_project）。"""
    assert (
        pre_tool_call(
            tool_name="read_file",
            args={
                "path": r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\artifacts\video_analysis_brief.json",
            },
        )
        is None
    )


def test_blocks_read_file_openmontage_source():
    """插件源码必须走 om_*，禁止 read_file 浏览。"""
    verdict = pre_tool_call(
        tool_name="read_file",
        args={
            "path": r"H:\work\OpenMontage\agent-hub\src\plugins\openmontage\lib\checkpoint.py",
        },
    )
    assert verdict is not None and verdict["action"] == "block"
    assert "om_" in verdict["message"]


def test_blocks_read_file_meta_skill():
    verdict = pre_tool_call(
        tool_name="read_file",
        args={
            "path": r"H:\work\OpenMontage\agent-hub\src\plugins\openmontage\skills\meta\video-reference-analyst.md",
            "label": "读元技能 video-reference-analyst",
        },
    )
    assert verdict is not None and verdict["action"] == "block"
    assert "skill_view" in verdict["message"]


def test_blocks_read_file_project_meta_and_checkpoint():
    for path in (
        r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\meta.json",
        r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\checkpoint_research.json",
        r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\checkpoints\research.json",
        r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\runs\abc123.json",
        r"H:\work\OpenMontage\.data\montage\projects\my-copy-01\.run.lock",
    ):
        verdict = pre_tool_call(tool_name="read_file", args={"path": path})
        assert verdict is not None and verdict["action"] == "block", path
        assert "om_project" in verdict["message"] or "om_job" in verdict["message"]


def test_allows_read_file_layer3_agent_skills():
    assert (
        pre_tool_call(
            tool_name="read_file",
            args={"path": r"H:\work\OpenMontage\.agents\skills\ffmpeg\SKILL.md"},
        )
        is None
    )


def test_blocks_wait_10min_label():
    verdict = pre_tool_call(
        tool_name="om_job",
        args={
            "project_id": "demo",
            "task_id": "abc",
            "label": "Wait 10min poll reference analysis 5",
        },
    )
    assert verdict is not None and verdict["action"] == "block"
    assert "15" in verdict["message"] or "60" in verdict["message"] or "轮询" in verdict["message"]


def test_blocks_fake_wait_90s_label_from_user_log():
    """用户日志实证：label「等 90 秒查 edit 重跑进度」却只跑 0.1s。"""
    for label in (
        "等 90 秒查 edit 重跑进度",
        "等 90 秒查 compose 进度",
        "等 90 秒查 publish 收尾",
        "wait 90s check edit progress",
    ):
        verdict = pre_tool_call(
            tool_name="om_job",
            args={"project_id": "demo", "task_id": "abc", "label": label},
        )
        assert verdict is not None and verdict["action"] == "block", label
        assert "假等待" in verdict["message"] or "om_job" in verdict["message"]

    allowed = pre_tool_call(
        tool_name="om_job",
        args={
            "project_id": "demo",
            "task_id": "abc",
            "label": "轮询 edit 进度",
        },
    )
    assert allowed is None


def test_blocks_poll_sleep_in_execute_code():
    verdict = pre_tool_call(
        tool_name="execute_code",
        args={
            "label": "等进度",
            "code": "import time; time.sleep(90)",
        },
    )
    assert verdict is not None and verdict["action"] == "block"


def test_blocks_long_sleep_terminal():
    verdict = pre_tool_call(
        tool_name="terminal",
        args={"label": "空等", "command": "sleep 600"},
    )
    assert verdict is not None and verdict["action"] == "block"


def test_blocks_stage_skipping(tmp_path, monkeypatch):
    """显式指定的 stage 与 next_stage 不符时拦截。"""
    import plugins.openmontage.governance as gov

    monkeypatch.setattr(
        gov,
        "_check_pipeline_bypass",
        lambda _payload: None,  # 隔离，只测阶段顺序
    )

    def fake_status(project_id):
        return {"next_stage": "script"}

    project_id = "smoke-stage-order"
    projects_root = tmp_path / "projects"
    (projects_root / project_id).mkdir(parents=True)
    (projects_root / project_id / "project.json").write_text("{}", encoding="utf-8")

    import plugins.openmontage.lib.paths as paths_mod
    import plugins.openmontage.lib.project_status as status_mod

    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", projects_root)
    monkeypatch.setattr(status_mod, "build_project_status", fake_status)

    blocked = pre_tool_call(
        tool_name="om_run", args={"project_id": project_id, "stage": "publish"}
    )
    assert blocked is not None and blocked["action"] == "block"
    assert "script" in blocked["message"]

    allowed = pre_tool_call(
        tool_name="om_run", args={"project_id": project_id, "stage": "script"}
    )
    assert allowed is None, "等于 next_stage 的阶段必须放行"


def test_omitting_stage_is_allowed():
    """不指定 stage 就是跑 next_stage，天然不可能跳。"""
    assert pre_tool_call(tool_name="om_run", args={"project_id": "whatever"}) is None


def test_om_run_spawns_without_asyncio_loop(tmp_path, monkeypatch):
    """CLI 同步工具上下文没有事件循环时，om_run 仍应调度后台 run_task。"""
    import json

    from plugins.openmontage.backlot import stage_runner
    from plugins.openmontage.exec_tools import handle_run

    project_id = "spawn-smoke"
    projects_root = tmp_path / "projects"
    project_dir = projects_root / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps({"pipeline_type": "reference-driven"}),
        encoding="utf-8",
    )

    import plugins.openmontage.lib.paths as paths_mod
    import plugins.openmontage.lib.project_status as status_mod

    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", projects_root)
    monkeypatch.setattr(
        status_mod,
        "build_project_status",
        lambda _pid: {"next_stage": "reference_analysis"},
    )

    scheduled: list[str] = []

    def fake_prepare(project_dir, **kwargs):
        task = stage_runner.RunTask(
            task_id="task123",
            project_dir=project_dir,
            project_id=project_id,
            stage="reference_analysis",
            pipeline_type="reference-driven",
        )
        stage_runner._TASKS[project_id] = task
        return task

    def fake_schedule(task, *, chain=True):
        scheduled.append(task.task_id)

    monkeypatch.setattr(stage_runner, "prepare_stage_run", fake_prepare)
    monkeypatch.setattr(stage_runner, "schedule_run_task", fake_schedule)

    payload = json.loads(handle_run({"project_id": project_id}))
    assert payload["ok"] is True
    assert payload["spawned"] is True
    assert scheduled == ["task123"]


# ─── 能力收口：从工具列表拿掉读文件 ───────────────────────────────────


def test_capability_lock_strips_read_file_from_llm_request():
    from plugins.openmontage.capability_lock import (
        llm_request_middleware,
        mark_session_lockdown,
        reset_lockdown_state_for_tests,
        tools_to_strip,
    )

    reset_lockdown_state_for_tests()
    sid = "lock-strip-1"
    mark_session_lockdown(sid, reason="test")
    banned = tools_to_strip(sid)
    assert "read_file" in banned
    assert "search_files" in banned
    assert "terminal" in banned
    assert "execute_code" in banned

    request = {
        "model": "x",
        "tools": [
            {"type": "function", "function": {"name": "om_job", "parameters": {}}},
            {"type": "function", "function": {"name": "read_file", "parameters": {}}},
            {"type": "function", "function": {"name": "search_files", "parameters": {}}},
            {"type": "function", "function": {"name": "terminal", "parameters": {}}},
            {"type": "function", "function": {"name": "execute_code", "parameters": {}}},
            {"type": "function", "function": {"name": "write_file", "parameters": {}}},
        ],
    }
    out = llm_request_middleware(request=request, session_id=sid)
    assert out is not None
    names = [t["function"]["name"] for t in out["request"]["tools"]]
    assert names == ["om_job", "write_file"]
    reset_lockdown_state_for_tests()


def test_capability_lock_blocks_read_file_at_pre_tool(monkeypatch):
    from plugins.openmontage.capability_lock import (
        mark_session_lockdown,
        reset_lockdown_state_for_tests,
    )

    reset_lockdown_state_for_tests()
    sid = "lock-block-1"
    mark_session_lockdown(sid, reason="test")
    blocked = pre_tool_call(
        tool_name="read_file",
        args={"path": "projects/x/artifacts/a.json"},
        session_id=sid,
    )
    assert blocked is not None and blocked["action"] == "block"
    assert "能力收口" in blocked["message"]
    blocked_term = pre_tool_call(
        tool_name="terminal",
        args={"command": "ls", "label": "列目录"},
        session_id=sid,
    )
    assert blocked_term is not None and blocked_term["action"] == "block"
    reset_lockdown_state_for_tests()


def test_capability_lock_unified_strips_terminal_without_busy():
    """锁定即统一拿掉 terminal/execute_code，不依赖跨进程 busy。"""
    from plugins.openmontage.capability_lock import (
        mark_session_lockdown,
        reset_lockdown_state_for_tests,
        tools_to_strip,
    )

    reset_lockdown_state_for_tests()
    sid = "lock-unified-1"
    mark_session_lockdown(sid, reason="test")
    banned = tools_to_strip(sid)
    assert "terminal" in banned
    assert "execute_code" in banned
    assert "read_file" in banned
    reset_lockdown_state_for_tests()


def test_capability_lock_skips_headless(monkeypatch):
    from plugins.openmontage.capability_lock import (
        mark_session_lockdown,
        reset_lockdown_state_for_tests,
        tools_to_strip,
    )

    reset_lockdown_state_for_tests()
    monkeypatch.setenv("OPENMONTAGE_HEADLESS_STAGE", "1")
    mark_session_lockdown("headless-sess", reason="test")
    assert tools_to_strip("headless-sess") == frozenset()
    reset_lockdown_state_for_tests()


def test_om_intent_activates_lockdown():
    from plugins.openmontage.capability_lock import (
        is_session_locked,
        reset_lockdown_state_for_tests,
    )
    from plugins.openmontage.skills import pre_llm_call

    reset_lockdown_state_for_tests()
    sid = "lock-intent-1"
    pre_llm_call(
        is_first_turn=True,
        user_message="帮我做一个短视频",
        session_id=sid,
    )
    assert is_session_locked(sid)
    reset_lockdown_state_for_tests()


def test_greeting_does_not_lockdown():
    from plugins.openmontage.capability_lock import (
        is_session_locked,
        reset_lockdown_state_for_tests,
    )
    from plugins.openmontage.skills import pre_llm_call

    reset_lockdown_state_for_tests()
    sid = "lock-hi-1"
    assert pre_llm_call(user_message="hi", session_id=sid) is None
    assert not is_session_locked(sid)
    reset_lockdown_state_for_tests()
