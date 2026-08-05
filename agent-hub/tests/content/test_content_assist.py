"""Tests for content assist (CR-75)."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from plugins.mxai.content.assist import (
    complete_content_assist,
    iter_content_assist_sse,
    resolve_mode,
)
from plugins.mxai.content.scenes import build_system_prompt, build_user_prompt


def test_resolve_mode_auto():
    assert resolve_mode("", "auto") == "generate"
    assert resolve_mode("  ", "auto") == "generate"
    assert resolve_mode("hello", "auto") == "optimize"
    assert resolve_mode("hello", "generate") == "generate"


def test_build_prompts_agent_soul():
    ctx = {"agent": "assistant", "max_length": 4000, "target_length": 800}
    sys = build_system_prompt("agent_soul", "markdown", ctx)
    user = build_user_prompt("generate", "", "agent_soul", "markdown", ctx)
    assert "人格" in sys
    assert "assistant" in sys
    assert "800" in sys
    assert "4000" in sys
    assert "勿堆砌" in sys or "够用即可" in sys
    assert "初稿" in user
    assert "800" in user
    assert "勿顶满" in user or "够用即可" in user


def test_build_prompts_agent_soul_defaults_use_target_not_max_only():
    sys = build_system_prompt("agent_soul", "markdown", {"agent": "wechat_chat"})
    assert "800" in sys
    assert "4000" in sys
    user = build_user_prompt("generate", "", "agent_soul", "markdown", {"agent": "wechat_chat"})
    assert "800" in user


def test_build_user_prompt_with_instruction():
    user = build_user_prompt(
        "generate",
        "",
        "agent_description",
        "plain",
        {"instruction": "语气活泼，突出售后"},
    )
    assert "用户补充要求" in user
    assert "语气活泼" in user

    user_opt = build_user_prompt(
        "optimize",
        "旧描述",
        "agent_description",
        "plain",
        {"instruction": "更简洁"},
    )
    assert "用户补充要求" in user_opt
    assert "更简洁" in user_opt
    assert "旧描述" in user_opt


def test_complete_mock_generate():
    from plugins.mxai.agents import hermes_agent

    hermes_agent.set_llm_override(None)
    import os

    os.environ["MXAI_MOCK"] = "1"
    try:
        out = complete_content_assist(
            scene="agent_description",
            fmt="plain",
            content="",
            mode="auto",
            context={"agent": "douyin"},
        )
        assert out["mode_used"] == "generate"
        assert "Mock" in out["content"] or "示例" in out["content"]
    finally:
        os.environ.pop("MXAI_MOCK", None)


def test_complete_mock_optimize():
    import os

    from plugins.mxai.agents import hermes_agent

    hermes_agent.set_llm_override(None)
    os.environ["MXAI_MOCK"] = "1"
    try:
        out = complete_content_assist(
            scene="agent_soul",
            fmt="markdown",
            content="# Old soul",
            mode="auto",
        )
        assert out["mode_used"] == "optimize"
        assert "Old soul" in out["content"] or "Mock" in out["content"]
    finally:
        os.environ.pop("MXAI_MOCK", None)


def test_invalid_scene_raises():
    with pytest.raises(HTTPException) as exc:
        complete_content_assist(scene="not_a_scene", fmt="plain", content="")
    assert exc.value.status_code == 422


def test_falls_back_to_hermes_when_gui_llm_not_ok(monkeypatch):
    """GUI 未选模型时仍走框架默认主模型，不 503 / 不 Mock。"""
    monkeypatch.delenv("MXAI_MOCK", raising=False)
    monkeypatch.setattr("plugins.mxai.cfg.llm_config.llm_config_ok", lambda: False)
    monkeypatch.setattr(
        "plugins.mxai.content.assist._complete_real",
        lambda _msgs, profile_id=None: "hermes default model output",
    )
    out = complete_content_assist(scene="agent_description", fmt="plain", content="")
    assert out["content"] == "hermes default model output"
    assert out["mode_used"] == "generate"


def test_complete_passes_profile_id_from_context(monkeypatch):
    monkeypatch.delenv("MXAI_MOCK", raising=False)
    captured: list[str | None] = []

    def fake_complete(_msgs, profile_id=None):
        captured.append(profile_id)
        return "scoped"

    monkeypatch.setattr("plugins.mxai.content.assist._complete_real", fake_complete)
    complete_content_assist(
        scene="agent_soul",
        fmt="markdown",
        content="",
        context={"agent": "wecom"},
    )
    assert captured == ["qiyeweixin_chat"]


def test_stream_real_deltas_runs_llm_in_worker_thread(monkeypatch):
    """LLM 流须在单 worker 线程完成；SSE 生成器经 queue 取 delta，避免 threadpool 跨 Context resume."""
    import threading

    scope_active: list[bool] = []
    worker_names: list[str] = []

    real_thread = threading.Thread

    class TrackThread(real_thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            worker_names.append(kwargs.get("name") or "")

    monkeypatch.setattr("plugins.mxai.content.assist.threading.Thread", TrackThread)

    class FakeCtx:
        def __enter__(self):
            scope_active.append(True)
            return self

        def __exit__(self, *args):
            scope_active.append(False)

    monkeypatch.setattr("plugins.mxai.cfg.agent_model_config.profile_llm_scope", lambda _pid: FakeCtx())

    class FakeDelta:
        content = "x"

    class FakeChoice:
        delta = FakeDelta()

    class FakeChunk:
        choices = [FakeChoice()]

    class FakeClient:
        base_url = "http://test"

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    def gen():
                        yield FakeChunk()

                    return gen()

    import agent.auxiliary_client as aux

    monkeypatch.setattr(aux, "_resolve_task_provider_model", lambda *a, **k: ("auto", "m", None, None, None))
    monkeypatch.setattr(aux, "_get_cached_client", lambda *a, **k: (FakeClient(), "m"))
    monkeypatch.setattr(aux, "_get_task_timeout", lambda *a, **k: 30)
    monkeypatch.setattr(
        aux,
        "_build_call_kwargs",
        lambda *a, **k: {"messages": a[2]},
    )

    from plugins.mxai.content.assist import _stream_real_deltas

    gen = _stream_real_deltas([{"role": "user", "content": "hi"}], "wechat_chat")
    first = next(gen)
    assert first == "x"
    assert scope_active == [True, False]
    assert "mxai-content-assist" in worker_names


def test_sse_mock_emits_events():
    import os

    os.environ["MXAI_MOCK"] = "1"
    try:
        chunks = list(
            iter_content_assist_sse(
                scene="agent_description",
                fmt="plain",
                content="",
            )
        )
        assert any("assist.start" in c for c in chunks)
        assert any("assist.delta" in c for c in chunks)
        assert any("assist.done" in c for c in chunks)
        done_line = next(c for c in chunks if "assist.done" in c)
        data = json.loads(done_line.split("data:", 1)[1].strip())
        assert data.get("content")
        assert data.get("mode_used") == "generate"
    finally:
        os.environ.pop("MXAI_MOCK", None)
