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

    def register_tool(self, name, **_kw):  # noqa: ANN001
        self.tools.append(name)

    def register_skill(self, name, path, description=""):  # noqa: ANN001
        assert Path(path).is_file(), f"技能文件不存在: {path}"
        self.skills.append(name)
        self.skill_paths.append(Path(path))

    def register_hook(self, hook_name, callback):  # noqa: ANN001
        assert callable(callback)
        self.hooks.append(hook_name)


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


def test_data_root_defaults_to_repo_root():
    """不注入时数据根等于仓库根 —— 独立签出的老行为。"""
    assert DATA_ROOT == REPO_ROOT


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
    verdict = pre_tool_call(tool_name="terminal", args={"command": command})
    assert verdict is not None, f"Rule Zero 应拦下绕流水线的脚本: {command}"
    assert verdict["action"] == "block"
    assert "Rule Zero" in verdict["message"]


@pytest.mark.parametrize(
    "command",
    ["ls projects/", "git status", "python -m plugins.openmontage.lib.project_status x"],
)
def test_allows_ordinary_commands(command):
    """对照组：正常命令必须放行，否则治理就成了瘫痪。"""
    assert pre_tool_call(tool_name="terminal", args={"command": command}) is None


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
