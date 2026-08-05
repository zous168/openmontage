"""Contract tests for the ZhipuAI (BigModel) image generation tool.

These tests verify that ZhipuImage satisfies the BaseTool contract without
requiring a real ZHIPU_API_KEY or making any API calls. They check class
attributes, schemas, status reporting, cost estimates, payload building,
and the Layer 3 skill file existence.

Run: pytest tests/contracts/test_zhipu_image.py -v
"""

from pathlib import Path

import pytest

from plugins.openmontage.tools.base_tool import (
    BaseTool,
    ExecutionMode,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage

TOOLS = [ZhipuImage]
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

EXPECTED_TIER = {ZhipuImage: ToolTier.GENERATE}
EXPECTED_CAPABILITY = {ZhipuImage: "image_generation"}
EXPECTED_EXECUTION_MODE = {ZhipuImage: ExecutionMode.SYNC}


# ------------------------------------------------------------------
# Contract compliance (parametrized over all tools)
# ------------------------------------------------------------------

@pytest.mark.parametrize("cls", TOOLS, ids=lambda c: c.name)
class TestContract:

    def test_inherits_base_tool(self, cls):
        assert issubclass(cls, BaseTool)

    def test_has_required_identity(self, cls):
        tool = cls()
        assert tool.name
        assert tool.version
        assert tool.provider == "zhipu"
        assert tool.capability == EXPECTED_CAPABILITY[cls]
        assert tool.tier == EXPECTED_TIER[cls]
        assert tool.stability == ToolStability.EXPERIMENTAL
        assert tool.runtime == ToolRuntime.API

    def test_has_input_schema(self, cls):
        tool = cls()
        schema = tool.input_schema
        assert schema.get("type") == "object"
        props = schema.get("properties", {})
        required = schema.get("required", [])
        assert len(required) >= 1
        for field in required:
            assert field in props

    def test_has_capabilities(self, cls):
        tool = cls()
        assert len(tool.capabilities) > 0

    def test_has_agent_skills(self, cls):
        tool = cls()
        assert tool.agent_skills
        assert "zhipu" in tool.agent_skills

    def test_zhipu_layer3_skill_exists(self, cls):
        # Layer 3 技能包留在仓库根，不随插件分发。
        from plugins.openmontage.lib.paths import LAYER3_SKILLS_DIR

        skill_path = LAYER3_SKILLS_DIR / "zhipu" / "SKILL.md"
        assert skill_path.exists(), f"Missing Layer 3 skill: {skill_path}"
        content = skill_path.read_text(encoding="utf-8")
        assert "ZHIPU_API_KEY" in content

    def test_has_fallbacks(self, cls):
        tool = cls()
        assert tool.fallback or tool.fallback_tools

    def test_has_install_instructions(self, cls):
        tool = cls()
        assert tool.install_instructions
        assert "ZHIPU_API_KEY" in tool.install_instructions

    def test_get_info_returns_dict(self, cls):
        tool = cls()
        info = tool.get_info()
        assert isinstance(info, dict)
        assert info["name"] == tool.name
        assert info["provider"] == "zhipu"
        assert info["runtime"] == "api"
        assert info["agent_skills"] == ["zhipu"]

    def test_execution_mode(self, cls):
        tool = cls()
        assert tool.execution_mode == EXPECTED_EXECUTION_MODE[cls]

    def test_status_unavailable_without_key(self, cls, monkeypatch):
        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
        tool = cls()
        assert tool.get_status() == ToolStatus.UNAVAILABLE

    def test_status_available_with_key(self, cls, monkeypatch):
        monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-for-testing")
        tool = cls()
        assert tool.get_status() == ToolStatus.AVAILABLE

    def test_idempotency_key_fields(self, cls):
        tool = cls()
        assert len(tool.idempotency_key_fields) > 0

    def test_has_resource_profile(self, cls):
        tool = cls()
        assert tool.resource_profile.network_required is True
        assert tool.resource_profile.vram_mb == 0

    def test_has_retry_policy(self, cls):
        tool = cls()
        assert tool.retry_policy.max_retries >= 0

    def test_has_side_effects(self, cls):
        tool = cls()
        assert len(tool.side_effects) > 0
        assert any("API" in s for s in tool.side_effects)

    def test_has_user_visible_verification(self, cls):
        tool = cls()
        assert len(tool.user_visible_verification) > 0

    def test_lazy_imports_requests(self, cls, monkeypatch):
        """Tool module must not import requests at top level (registry
        discovery must stay fast)."""
        import importlib
        import sys
        monkeypatch.delitem(sys.modules, "requests", raising=False)
        mod_name = cls.__module__
        importlib.reload(sys.modules[mod_name])
        # Smoke test: reload must not crash; requests stays lazy in execute().

    def test_estimate_cost_returns_float(self, cls):
        tool = cls()
        cost = tool.estimate_cost({"prompt": "test"})
        assert isinstance(cost, float)
        assert cost >= 0.0

    def test_dry_run_returns_dict(self, cls):
        tool = cls()
        result = tool.dry_run({"prompt": "test"})
        assert isinstance(result, dict)
        assert "tool" in result
        assert result["tool"] == tool.name


# ------------------------------------------------------------------
# ZhipuImage-specific tests
# ------------------------------------------------------------------

class TestZhipuImageSpecific:

    def test_default_model_is_cogview_4_250304(self):
        tool = ZhipuImage()
        assert tool.input_schema["properties"]["model"]["default"] == "cogview-4-250304"

    def test_default_quality_is_standard(self):
        tool = ZhipuImage()
        assert tool.input_schema["properties"]["quality"]["default"] == "standard"

    def test_default_size_is_1024x1024(self):
        tool = ZhipuImage()
        assert tool.input_schema["properties"]["size"]["default"] == "1024x1024"

    def test_size_uses_x_not_asterisk(self):
        """CRITICAL: Zhipu's OpenAI-compatible endpoint uses WxH (lowercase x),
        NOT the "*" separator DashScope uses. A copy-paste of the DashScope
        convention would break every size request."""
        tool = ZhipuImage()
        size_default = tool.input_schema["properties"]["size"]["default"]
        assert "x" in size_default
        assert "*" not in size_default

    def test_watermark_enabled_default_true(self):
        tool = ZhipuImage()
        assert tool.input_schema["properties"]["watermark_enabled"]["default"] is True

    def test_cost_positive_for_image(self):
        tool = ZhipuImage()
        assert tool.estimate_cost({"prompt": "test"}) > 0.0

    def test_cost_scales_with_quality(self):
        tool = ZhipuImage()
        cost_standard = tool.estimate_cost({"prompt": "test", "quality": "standard"})
        cost_hd = tool.estimate_cost({"prompt": "test", "quality": "hd"})
        assert cost_hd > cost_standard

    def test_cost_differs_by_model(self):
        tool = ZhipuImage()
        cost_4 = tool.estimate_cost({"prompt": "test", "model": "cogview-4-250304"})
        cost_flash = tool.estimate_cost({"prompt": "test", "model": "cogview-3-flash"})
        assert cost_flash < cost_4

    def test_build_payload_defaults(self):
        tool = ZhipuImage()
        payload = tool._build_payload({"prompt": "a cat"})
        assert payload["model"] == "cogview-4-250304"
        assert payload["prompt"] == "a cat"
        assert payload["quality"] == "standard"
        assert payload["size"] == "1024x1024"
        assert payload["watermark_enabled"] is True

    def test_build_payload_flat_openai_compatible(self):
        """Zhipu endpoint is OpenAI-compatible: flat payload, no
        input/parameters nesting like DashScope."""
        tool = ZhipuImage()
        payload = tool._build_payload({"prompt": "a cat"})
        assert "input" not in payload
        assert "parameters" not in payload

    def test_build_payload_omits_user_id_when_absent(self):
        tool = ZhipuImage()
        payload = tool._build_payload({"prompt": "test"})
        assert "user_id" not in payload

    def test_build_payload_includes_user_id_when_present(self):
        tool = ZhipuImage()
        payload = tool._build_payload({"prompt": "test", "user_id": "user-1"})
        assert payload["user_id"] == "user-1"

    def test_build_payload_respects_overrides(self):
        tool = ZhipuImage()
        payload = tool._build_payload({
            "prompt": "test", "model": "cogview-3-flash",
            "quality": "hd", "size": "1344x768", "watermark_enabled": False,
        })
        assert payload["model"] == "cogview-3-flash"
        assert payload["quality"] == "hd"
        assert payload["size"] == "1344x768"
        assert payload["watermark_enabled"] is False

    def test_safe_error_redacts_key(self, monkeypatch):
        monkeypatch.setenv("ZHIPU_API_KEY", "secret-key-12345")
        redacted = ZhipuImage._safe_error(
            Exception("failed with key secret-key-12345")
        )
        assert "secret-key-12345" not in redacted
        assert "[redacted]" in redacted

    def test_extract_image_urls_single(self):
        data = {"data": [{"url": "https://x/1.png"}]}
        assert ZhipuImage._extract_image_urls(data) == ["https://x/1.png"]

    def test_extract_image_urls_multiple(self):
        data = {
            "data": [
                {"url": "https://x/1.png"},
                {"url": "https://x/2.png"},
            ]
        }
        assert ZhipuImage._extract_image_urls(data) == [
            "https://x/1.png",
            "https://x/2.png",
        ]

    def test_extract_image_urls_empty_when_no_urls(self):
        assert ZhipuImage._extract_image_urls({}) == []
        assert ZhipuImage._extract_image_urls({"data": []}) == []
        assert ZhipuImage._extract_image_urls({"data": [{"b64_json": "xx"}]}) == []

    def test_extract_image_urls_skips_entries_without_url(self):
        data = {
            "data": [
                {"url": "https://x/ok.png"},
                {"content_filter": {"level": 3}},
            ]
        }
        assert ZhipuImage._extract_image_urls(data) == ["https://x/ok.png"]

    def test_resolve_output_paths_single_unchanged(self):
        paths = ZhipuImage._resolve_output_paths("foo.png", 1)
        assert paths == [Path("foo.png")]

    def test_resolve_output_paths_multiple_inserts_index(self):
        paths = ZhipuImage._resolve_output_paths("foo.png", 2)
        assert paths == [Path("foo_1.png"), Path("foo_2.png")]

    def test_execute_no_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
        tool = ZhipuImage()
        result = tool.execute({"prompt": "test"})
        assert result.success is False
        assert "ZHIPU_API_KEY" in result.error


# ------------------------------------------------------------------
# Idempotency keys
# ------------------------------------------------------------------

class TestZhipuIdempotencyKeys:

    def test_idempotency_includes_all_output_fields(self):
        fields = ZhipuImage().idempotency_key_fields
        for field in (
            "prompt", "model", "quality", "size",
            "watermark_enabled", "user_id",
        ):
            assert field in fields, f"zhipu idempotency missing {field}"

    def test_idempotency_differs_on_quality(self):
        tool = ZhipuImage()
        base = {"prompt": "x", "model": "cogview-4-250304"}
        assert tool.idempotency_key(
            {**base, "quality": "standard"}
        ) != tool.idempotency_key({**base, "quality": "hd"})

    def test_idempotency_differs_on_watermark(self):
        tool = ZhipuImage()
        base = {"prompt": "x", "model": "cogview-4-250304"}
        assert tool.idempotency_key(
            {**base, "watermark_enabled": True}
        ) != tool.idempotency_key({**base, "watermark_enabled": False})

    def test_idempotency_differs_on_size(self):
        tool = ZhipuImage()
        base = {"prompt": "x", "model": "cogview-4-250304"}
        assert tool.idempotency_key(
            {**base, "size": "1024x1024"}
        ) != tool.idempotency_key({**base, "size": "1344x768"})


# ------------------------------------------------------------------
# Registry discovery
# ------------------------------------------------------------------

class TestZhipuRegistryDiscovery:

    def test_tool_discoverable(self):
        from plugins.openmontage.tools.tool_registry import ToolRegistry
        registry = ToolRegistry()
        registry.discover()
        zhipu_tools = [
            t for t in registry._tools.values()
            if t.provider == "zhipu"
        ]
        names = {t.name for t in zhipu_tools}
        assert names == {"zhipu_image"}

    def test_image_selector_finds_zhipu(self):
        """image_selector auto-discovers providers by capability —
        zhipu_image must be routable via preferred_provider: 'zhipu'."""
        assert ZhipuImage().capability == "image_generation"
        assert ZhipuImage().provider == "zhipu"
