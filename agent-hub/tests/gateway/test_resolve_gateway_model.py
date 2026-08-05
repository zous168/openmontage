"""网关 run 时 model 解析：profile 缺 model 时回退根（default）全局默认.

回归（A-Main 助理 moark 400）：``assistant`` profile 自身无 ``model:`` 块，
``_load_gateway_config()`` raw 读得空 → 旧实现返回 ``''`` → LLM 请求 ``model=''`` →
provider 400。修复后回退 ``load_config()``（overlay 合并根 ``config.yaml``）的全局默认。
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gateway import run as gw_run  # noqa: E402


def test_profile_own_model_wins_no_overlay_fallback(monkeypatch) -> None:
    """profile 自带 model → 直接用，不触发 overlay 回退（load_config 不应被调）。"""
    monkeypatch.setattr(
        gw_run, "_load_gateway_config", lambda: {"model": {"provider": "moark", "default": "MiniMax-M2.7"}}
    )

    def _boom():  # load_config 一旦被调即测试失败
        raise AssertionError("load_config overlay fallback should not run when profile has model")

    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    assert gw_run._resolve_gateway_model() == "MiniMax-M2.7"


def test_empty_profile_model_falls_back_to_root_default(monkeypatch) -> None:
    """profile 无 model 块 → 回退 load_config()（overlay 合并根）的全局默认。"""
    monkeypatch.setattr(gw_run, "_load_gateway_config", lambda: {"platform_toolsets": {}})  # 无 model
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"model": {"provider": "moark", "default": "MiniMax-M2.7"}},
    )
    assert gw_run._resolve_gateway_model() == "MiniMax-M2.7"


def test_explicit_config_never_triggers_overlay_fallback(monkeypatch) -> None:
    """显式传入 config（测试/特定上下文）→ 即便无 model 也不回退，保持原契约。"""
    def _boom(*a, **k):
        raise AssertionError("explicit config must not trigger overlay fallback")

    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    assert gw_run._resolve_gateway_model({"model": {}}) == ""


def test_str_model_value(monkeypatch) -> None:
    monkeypatch.setattr(gw_run, "_load_gateway_config", lambda: {"model": "foo-1"})
    assert gw_run._resolve_gateway_model() == "foo-1"
