"""ZhipuAI (BigModel / 智谱开放平台) image generation via GLM/CogView models.

Uses the OpenAI-compatible images/generations endpoint. The response
contains a temporary image URL (valid ~30 days) that must be downloaded
separately. CogView-4 renders Chinese text in images accurately, which
makes it a strong fit for Chinese-language explainer videos.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class ZhipuImage(BaseTool):
    name = "zhipu_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "zhipu"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set ZHIPU_API_KEY to your ZhipuAI API key.\n"
        "  Get one at https://bigmodel.cn/usercenter/proj-mgmt/apikeys"
    )
    fallback = "dashscope_image"
    fallback_tools = [
        "dashscope_image",
        "grok_image",
        "openai_image",
        "flux_image",
        "recraft_image",
    ]
    agent_skills = ["zhipu"]

    capabilities = ["generate_image", "text_to_image"]
    supports = {
        "multiple_outputs": False,
        "aspect_ratio": True,
        "resolution": True,
        "negative_prompt": False,
        "seed": False,
    }
    best_for = [
        "high-quality image generation with GLM/CogView-4 models",
        "accurate Chinese text rendering inside images (CogView-4)",
        "cost-effective generation via ZhipuAI BigModel (~¥0.06/image)",
    ]
    not_good_for = [
        "offline generation",
        "image editing (use grok_image edit mode)",
        "multi-image batches (one image per API call)",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Text prompt. CogView-4 understands Chinese and can "
                    "render Chinese text inside the image."
                ),
            },
            "model": {
                "type": "string",
                "enum": [
                    "cogview-4-250304",
                    "cogview-4",
                    "cogview-3-flash",
                    "glm-image",
                ],
                "default": "cogview-4-250304",
            },
            "quality": {
                "type": "string",
                "enum": ["hd", "standard"],
                "default": "standard",
                "description": (
                    "cogview-4 series supports hd/standard; glm-image is hd-only."
                ),
            },
            "size": {
                "type": "string",
                "enum": [
                    "1024x1024",
                    "768x1344",
                    "864x1152",
                    "1344x768",
                    "1152x864",
                    "1440x720",
                    "720x1440",
                ],
                "default": "1024x1024",
                "description": (
                    'Image size as "WxH" (lowercase x separator, OpenAI-compatible '
                    '— NOT the "*" used by DashScope). Size for cogview-4 series; '
                    "glm-image is fixed at 1280x1280."
                ),
            },
            "watermark_enabled": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Add ZhipuAI watermark. Disabling requires signing a "
                    "disclaimer with ZhipuAI."
                ),
            },
            "user_id": {
                "type": "string",
                "description": "Optional end-user identifier for billing/audit.",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["rate_limit", "timeout"]
    )
    idempotency_key_fields = [
        "prompt",
        "model",
        "quality",
        "size",
        "watermark_enabled",
        "user_id",
    ]
    side_effects = [
        "writes image file to output_path",
        "calls ZhipuAI (BigModel) image generation API",
    ]
    user_visible_verification = [
        "Inspect generated image for relevance and quality"
    ]

    ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/images/generations"

    def get_status(self) -> ToolStatus:
        if os.environ.get("ZHIPU_API_KEY"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # Per-image estimate: cogview-4-250304 standard ~¥0.06 ≈ $0.008.
        # hd quality roughly doubles the price; cogview-3-flash is cheaper.
        model = inputs.get("model", "cogview-4-250304")
        per_image = {
            "cogview-4-250304": 0.008,
            "cogview-4": 0.008,
            "cogview-3-flash": 0.005,
            "glm-image": 0.010,
        }.get(model, 0.008)
        if inputs.get("quality", "standard") == "hd" and model.startswith("cogview"):
            per_image *= 2.0
        return per_image

    def dry_run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        base = super().dry_run(inputs)
        base["model"] = inputs.get("model", "cogview-4-250304")
        base["quality"] = inputs.get("quality", "standard")
        base["size"] = inputs.get("size", "1024x1024")
        return base

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = os.environ.get("ZHIPU_API_KEY")
        if not api_key:
            return ToolResult(
                success=False,
                error="ZHIPU_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        try:
            payload = self._build_payload(inputs)
            response = requests.post(
                self.ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()

            image_urls = self._extract_image_urls(data)
            if not image_urls:
                return ToolResult(
                    success=False,
                    error="ZhipuAI returned no image URLs",
                )

            # URLs expire after ~30 days; download every one to disk now.
            output_paths = self._resolve_output_paths(
                inputs.get("output_path", "zhipu_image.png"),
                count=len(image_urls),
            )
            for path, url in zip(output_paths, image_urls):
                download = requests.get(url, timeout=120)
                download.raise_for_status()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(download.content)

            n_generated = len(image_urls)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"ZhipuAI image generation failed: {self._safe_error(e)}",
            )

        return ToolResult(
            success=True,
            data={
                "provider": "zhipu",
                "model": payload["model"],
                "prompt": inputs["prompt"],
                "size": payload["size"],
                "quality": payload.get("quality"),
                "output": str(output_paths[0]),
                "outputs": [str(p) for p in output_paths],
                "images_generated": n_generated,
                "usage": data.get("usage", {}),
                "content_filter": data.get("content_filter"),
            },
            artifacts=[str(p) for p in output_paths],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=payload["model"],
        )

    @staticmethod
    def _extract_image_urls(data: dict[str, Any]) -> list[str]:
        """Collect image URLs from the OpenAI-compatible data array.

        Each entry carries a temporary `url` (valid ~30 days). Entries
        without a url (e.g. content-filtered results) are skipped.
        """
        urls: list[str] = []
        for item in data.get("data", []):
            url = item.get("url")
            if url:
                urls.append(url)
        return urls

    @staticmethod
    def _resolve_output_paths(base: str, count: int) -> list[Path]:
        """Derive distinct paths for `count` images. Single image keeps the
        base path unchanged; multiple images insert an index before the
        extension (foo.png -> foo_1.png, foo_2.png, ...)."""
        base_path = Path(base)
        if count <= 1:
            return [base_path]
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        return [parent / f"{stem}_{i}{suffix}" for i in range(1, count + 1)]

    def _build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": inputs.get("model", "cogview-4-250304"),
            "prompt": inputs["prompt"],
            "quality": inputs.get("quality", "standard"),
            "size": inputs.get("size", "1024x1024"),
            "watermark_enabled": bool(inputs.get("watermark_enabled", True)),
        }
        if inputs.get("user_id"):
            payload["user_id"] = inputs["user_id"]
        return payload

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return str(exc).replace(os.environ.get("ZHIPU_API_KEY", ""), "[redacted]")
