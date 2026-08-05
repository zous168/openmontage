"""agent-hub 共享 pytest fixtures。

``plugins/mxai`` 在移植进 OpenMontage 时被剥离，但 324 个测试里有 272 个仍依赖它。
过去这些死测试让整个 conftest 导入失败，**一个模块卡死全套收集** —— CI 既跑不出绿灯，
也跑不出有意义的红灯。

现在改为在收集阶段识别并跳过它们（见 ``pytest_ignore_collect``），
让剩余 52 个内核测试能真实运行。详见 ``agent-hub/UPSTREAM.md``。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 标识"依赖已移除的 plugins.mxai"的记号：直接 import，或使用只有 mxai conftest 才提供的 fixture。
_MXAI_MARKERS = (
    "plugins.mxai",
    "plugins/mxai",
    "mxai_env",
    "mxai_client",
    "arm_test_queue",
    "stub_rpa_bridge_for_tests",
)

_ignored_mxai_modules: list[str] = []


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """跳过依赖已移除的 ``plugins.mxai`` 的测试模块。

    返回 ``None`` 而非 ``False``，以免抢占其他插件的忽略决策。
    """
    if collection_path.suffix != ".py" or not collection_path.name.startswith("test_"):
        return None
    try:
        source = collection_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if any(marker in source for marker in _MXAI_MARKERS):
        _ignored_mxai_modules.append(collection_path.name)
        return True
    return None


def pytest_report_collectionfinish(config: pytest.Config) -> list[str] | None:
    """把跳过数量摆在收集摘要里，避免"绿灯"掩盖缺失的覆盖面。"""
    if not _ignored_mxai_modules:
        return None
    return [
        f"跳过 {len(_ignored_mxai_modules)} 个测试模块："
        "依赖已从本仓库移除的 plugins.mxai（见 agent-hub/UPSTREAM.md）"
    ]


# 显式放开时才允许 pytest 进程 POST 真实 Automan /api/open/hooks（跑本机工作流）。
_ALLOW_REAL_AUTOMAN_ENV = "MXAI_ALLOW_REAL_AUTOMAN"


@pytest.fixture(autouse=True)
def _block_real_automan_workflow_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI/单测默认禁止 POST 真实 Automan hooks（触发工作流）。

    用例若自备 Fake ``httpx.Client``（替换整个 Client）不受影响；
    真要打本机 Automan 须显式 ``MXAI_ALLOW_REAL_AUTOMAN=1``（每次 POST 时读 env）。
    """
    import httpx

    real_client = httpx.Client

    class _GuardedClient(real_client):
        def post(self, url: Any, *args: Any, **kwargs: Any) -> Any:
            u = str(url)
            if (
                "/api/open/hooks/" in u
                and os.environ.get(_ALLOW_REAL_AUTOMAN_ENV, "").strip() != "1"
            ):
                raise RuntimeError(
                    "pytest 禁止打真实 Automan 工作流 "
                    f"(POST {u})。请使用 Fake httpx，"
                    f"或显式设置 {_ALLOW_REAL_AUTOMAN_ENV}=1。"
                )
            return super().post(url, *args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _GuardedClient)


@pytest.fixture
def messaging_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(cfg_mod, "get_env_path", lambda: env_path)
    monkeypatch.setenv("MXAI_MOCK", "1")

    from hermes_cli.web_routes.oauth_messaging import router as messaging_router

    app = FastAPI()
    app.include_router(messaging_router)
    return TestClient(app)
