"""Static composition fallback when no remote video provider is configured."""

from __future__ import annotations

import pytest

from tools.base_tool import ToolStatus
from tools.video import _shared


def test_local_generation_unavailable_without_stack(monkeypatch):
    monkeypatch.setattr(_shared, "_local_stack_ready", lambda: False)
    monkeypatch.setattr(_shared, "local_generation_enabled", lambda: True)
    assert _shared.local_generation_status() == ToolStatus.UNAVAILABLE


def test_local_generation_explicit_enable(monkeypatch):
    monkeypatch.setattr(_shared, "_local_stack_ready", lambda: True)
    monkeypatch.setattr(_shared, "local_generation_enabled", lambda: True)
    assert _shared.local_generation_status() == ToolStatus.AVAILABLE


def test_local_gpu_never_auto_activates(monkeypatch):
    monkeypatch.setattr(_shared, "_local_stack_ready", lambda: True)
    monkeypatch.setattr(_shared, "local_generation_enabled", lambda: False)
    monkeypatch.setattr(_shared, "local_auto_fallback_enabled", lambda: True)
    monkeypatch.setattr(_shared, "any_remote_video_provider_available", lambda: False)
    assert _shared.local_auto_fallback_active() is False
    assert _shared.local_generation_status() == ToolStatus.UNAVAILABLE


def test_static_composition_fallback_when_no_remote(monkeypatch):
    monkeypatch.setattr(_shared, "local_auto_fallback_enabled", lambda: True)
    monkeypatch.setattr(_shared, "any_remote_video_provider_available", lambda: False)
    assert _shared.static_composition_fallback_active() is True


def test_static_composition_fallback_skipped_when_remote_exists(monkeypatch):
    monkeypatch.setattr(_shared, "local_auto_fallback_enabled", lambda: True)
    monkeypatch.setattr(_shared, "any_remote_video_provider_available", lambda: True)
    assert _shared.static_composition_fallback_active() is False


def test_default_local_provider_id_defaults_to_ltx(monkeypatch):
    monkeypatch.delenv("VIDEO_GEN_LOCAL_MODEL", raising=False)
    assert _shared.default_local_provider_id() == "ltx"


def test_video_selector_does_not_prefer_local_on_auto_fallback(monkeypatch):
    from tools.base_tool import ToolStatus as TS
    from tools.video.video_selector import VideoSelector

    class _LocalStub:
        capability = "video_generation"
        name = "ltx_video_local"
        provider = "ltx"
        best_for = ["local"]
        supports = {"text_to_video": True, "image_to_video": True}
        input_schema = {"properties": {"prompt": {}}}

        def get_status(self):
            return TS.UNAVAILABLE

        def is_operation_available(self, operation: str) -> bool:
            return True

        def get_info(self):
            return {"name": self.name, "provider": self.provider, "agent_skills": [], "best_for": self.best_for}

    def fake_rank(candidates, task_context):  # noqa: ANN001
        return []

    monkeypatch.setattr("lib.scoring.rank_providers", fake_rank)
    monkeypatch.setattr(_shared, "static_composition_fallback_active", lambda: True)

    tool, _ = VideoSelector()._select_best_tool(
        {"preferred_provider": "auto"},
        [_LocalStub()],
        {},
    )
    assert tool is None


def test_video_selector_execute_returns_static_fallback_payload(monkeypatch):
    from tools.base_tool import ToolStatus as TS
    from tools.video.video_selector import VideoSelector

    class _UnavailableStub:
        name = "ltx_video_local"
        provider = "ltx"
        runtime = None
        best_for = []
        supports = {"text_to_video": True}
        input_schema = {"properties": {"prompt": {}}}

        def get_status(self):
            return TS.UNAVAILABLE

        def is_operation_available(self, operation: str) -> bool:
            return True

        def get_info(self):
            return {"agent_skills": [], "best_for": []}

    selector = VideoSelector()
    monkeypatch.setattr(selector, "_providers", lambda: [_UnavailableStub()])
    monkeypatch.setattr(_shared, "static_composition_fallback_active", lambda: True)

    result = selector.execute({"prompt": "test scene", "operation": "text_to_video"})
    assert result.success is False
    assert result.data["fallback_strategy"] == "static_composition"
    assert "image_selector" in result.data["recommended_tools"]
    assert "video_compose" in result.data["recommended_tools"]
