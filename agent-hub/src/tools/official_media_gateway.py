"""官方算力渠道：图/视频经 llm-gateway（设备 JWT），平台持 FAL_KEY。

BYOK（本机 ``FAL_KEY``）优先直连 FAL，不走本模块。
无独立 /meter；计量与 402 硬拦均在网关 hooks。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

from core.platform.gateway_base_url import resolve_llm_gateway_base_url

LLM_GATEWAY_BASE_URL_ENV = "LLM_GATEWAY_BASE_URL"


def official_gateway_base_url() -> str:
    return resolve_llm_gateway_base_url()


def current_device_jwt() -> str:
    try:
        from core.platform.device.device_auth_service import get_fresh_device_access_token

        return get_fresh_device_access_token()
    except Exception:  # noqa: BLE001
        return ""


def resolve_official_media_gateway() -> Optional[Tuple[str, str]]:
    """
    官方媒体网关可用时返回 ``(base_url, device_jwt)``。

    BYOK：本机已配置 ``FAL_KEY`` 时返回 None（保留直连）。
    """
    from tools.tool_backend_helpers import fal_key_is_configured

    if fal_key_is_configured():
        return None
    base = official_gateway_base_url()
    if not base:
        return None
    jwt = current_device_jwt()
    if not jwt:
        return None
    return base, jwt


def official_media_gateway_available() -> bool:
    return resolve_official_media_gateway() is not None


def credits_insufficient_message() -> str:
    """媒体/音色等 REST 面：固定中文短提示（勿跟会话 i18n 语言走英文）。"""
    return "平台算力点不足，请在管理后台（CS）为商户充值算力点后再试。"


def is_credits_insufficient_error(message: str) -> bool:
    raw = (message or "").strip()
    if not raw:
        return False
    low = raw.lower()
    return (
        "insufficient_credits" in low
        or "insufficient compute credits" in low
        or "算力点不足" in raw
        or "平台算力点不足" in raw
    )


def raise_if_credits_http_error(status_code: int, body: str = "") -> None:
    """网关 402 → 友好提示（与 conversation_loop 官方渠道一致）。"""
    if int(status_code) == 402:
        raise ValueError(credits_insufficient_message())


def extract_gateway_error_message(body: Any, fallback: str = "") -> str:
    """从网关/OpenAI 风格错误 JSON 取 message（兼容 detail.error / error）。"""
    if not isinstance(body, dict):
        return (fallback or "")[:800]
    err = body.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])[:800]
    if isinstance(err, str) and err.strip():
        return err.strip()[:800]
    detail = body.get("detail")
    if isinstance(detail, dict):
        nested = detail.get("error")
        if isinstance(nested, dict) and nested.get("message"):
            return str(nested["message"])[:800]
        if detail.get("message"):
            return str(detail["message"])[:800]
    if isinstance(detail, str) and detail.strip():
        return detail.strip()[:800]
    if body.get("message"):
        return str(body["message"])[:800]
    return (fallback or "")[:800]


def humanize_speech_error(message: str, *, status_code: int | None = None) -> str:
    """把上游英文/代码错误转成前端可读中文（有明细则优先保留明细）。"""
    raw = (message or "").strip()
    if not raw:
        code = f"HTTP {status_code}" if status_code else "未知状态"
        return f"语音合成失败（网关无错误正文，{code}）"
    low = raw.lower()
    if is_credits_insufficient_error(raw) or ("402" in low and "credit" in low):
        return credits_insufficient_message()
    if "freetieronly" in low or "free quota exhausted" in low or "allocationquota" in low:
        return (
            "百炼语音免费额度已用尽：请充值，或在百炼控制台关闭「仅用免费额度」，"
            "或改用 IndexTTS 等其它 speech 模型"
        )
    if "时长不能超过" in raw or ("120" in raw and ("秒" in raw or "second" in low)):
        # IndexTTS：参考音最长 120 秒（日志曾见 372 秒被拒）
        return (
            "参考音频超过 IndexTTS 上限（120 秒）。"
            "请裁剪到 3–30 秒清晰人声后重新克隆（Hub 新版本会自动截断并转 wav）"
        )
    if "prompt_audio" in low and (
        ":8900" in raw or "minio" in low or "127.0.0.1" in raw
    ):
        return (
            "参考音频仍是内网存储地址，云端 TTS 无法下载。"
            "请删除该音色后重新克隆（使用 OSS 公网地址）"
        )
    if "prompt_audio_url" in low and ("is not valid" in low or "not valid" in low):
        if "/api/public/v1/voice/ref-audio" in raw or "voice/ref-audio" in raw:
            return (
                "参考音频仍是已废弃的 CS 开放链，IndexTTS 无法稳定拉取。"
                "请删除该音色后重新克隆以使用 OSS 永久公网地址"
            )
        if "accessdenied" in low or "403" in raw or ":8900" in raw:
            return (
                "参考音频地址无法被语音服务拉取（内网/私有桶）。"
                "请重新克隆音色以生成 OSS 公网地址"
            )
        return (
            "IndexTTS 拒绝参考音频 URL（is not valid）。"
            "请确认文件为可播放的 wav/mp3，并重新克隆"
        )
    if "accessdenied" in low or "access denied" in low:
        return (
            "参考音频地址无法被语音服务拉取。"
            "请重新克隆音色以生成 OSS 公网地址"
        )
    if raw in {"Internal server error", "Internal Server Error"}:
        # 旧网关未透传时的诊断；发版含 speech 路由包裹后应不再落到这里
        sc = status_code or 500
        return (
            f"语音网关 HTTP {sc} 且未透传上游明细（多为旧版 llm-gateway）。"
            "请发布含 audio_speech error surface 的网关后重试；"
            "并在网关日志搜索 audio_speech(): Exception 查看真实原因"
        )
    return raw


def audio_speech(
    *,
    base_url: str,
    jwt: str,
    model: str,
    input_text: str,
    voice: str,
    response_format: str = "mp3",
    extra_body: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
) -> bytes:
    """POST ``{base}/v1/audio/speech``（OpenAI 兼容 TTS 面），返回音频或 enroll JSON bytes。"""
    import httpx

    url = f"{base_url.rstrip('/')}/v1/audio/speech"
    payload: Dict[str, Any] = {
        "model": model,
        "input": input_text,
        "voice": voice,
        "response_format": response_format,
    }
    if extra_body:
        payload["extra_body"] = extra_body
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
        "Accept": "audio/*,application/json,application/octet-stream",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code == 402:
        raise_if_credits_http_error(402, resp.text)
    if resp.status_code >= 400:
        fallback = (resp.text or "")[:800]
        try:
            detail = extract_gateway_error_message(resp.json(), fallback=fallback)
        except Exception:
            detail = fallback
        logger.warning(
            "audio/speech failed status=%s model=%s detail=%s body=%s",
            resp.status_code,
            model,
            detail[:300],
            fallback[:300],
        )
        detail = humanize_speech_error(detail, status_code=resp.status_code)
        raise ValueError(f"Official audio speech HTTP {resp.status_code}: {detail}")
    if not resp.content:
        raise ValueError("Official audio speech returned empty body")
    return resp.content


def images_generations(
    *,
    base_url: str,
    jwt: str,
    model: str,
    prompt: str,
    n: int = 1,
    extra: Optional[Dict[str, Any]] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """POST ``{base}/v1/images/generations``（OpenAI 兼容 image 面）。"""
    import httpx

    url = f"{base_url.rstrip('/')}/v1/images/generations"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": max(1, int(n or 1)),
    }
    if extra:
        payload.update(extra)

    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code == 402:
        raise_if_credits_http_error(402, resp.text)
    if resp.status_code >= 400:
        raise ValueError(
            f"Official image gateway HTTP {resp.status_code}: {resp.text[:500]}"
        )
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Official image gateway returned non-object JSON")
    return data


def fal_queue_submit(
    *,
    base_url: str,
    jwt: str,
    endpoint: str,
    arguments: Dict[str, Any],
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST ``{base}/fal/{endpoint}`` → FAL queue submit（经网关 pass-through）。"""
    import httpx

    ep = endpoint.strip().lstrip("/")
    url = f"{base_url.rstrip('/')}/fal/{ep}"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=arguments, headers=headers)
    if resp.status_code == 402:
        raise_if_credits_http_error(402, resp.text)
    if resp.status_code >= 400:
        raise ValueError(
            f"Official FAL queue submit HTTP {resp.status_code}: {resp.text[:500]}"
        )
    data = resp.json()
    if not isinstance(data, dict) or not data.get("request_id"):
        raise ValueError("Official FAL queue submit missing request_id")
    return data


def fal_queue_result(
    *,
    base_url: str,
    jwt: str,
    endpoint: str,
    request_id: str,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    """轮询 ``{base}/fal/{endpoint}/requests/{id}/status`` 直至完成，再取结果。"""
    import httpx

    ep = endpoint.strip().lstrip("/")
    rid = request_id.strip()
    root = f"{base_url.rstrip('/')}/fal/{ep}/requests/{rid}"
    status_url = f"{root}/status"
    result_url = root
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/json",
    }
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=60.0) as client:
        while time.monotonic() < deadline:
            status_resp = client.get(status_url, headers=headers)
            if status_resp.status_code == 402:
                raise_if_credits_http_error(402, status_resp.text)
            if status_resp.status_code >= 400:
                raise ValueError(
                    f"Official FAL status HTTP {status_resp.status_code}: "
                    f"{status_resp.text[:500]}"
                )
            status_body = status_resp.json() if status_resp.content else {}
            st = str(
                (status_body or {}).get("status")
                or (status_body or {}).get("detail")
                or ""
            ).upper()
            if st in {"COMPLETED", "OK", "SUCCESS"} or (
                isinstance(status_body, dict) and status_body.get("video")
            ):
                break
            if st in {"FAILED", "ERROR", "CANCELLED"}:
                raise ValueError(f"Official FAL job failed: {status_body}")
            time.sleep(poll_interval)
        else:
            raise TimeoutError(
                f"Official FAL job timed out after {timeout}s (request_id={rid})"
            )

        result_resp = client.get(result_url, headers=headers)
        if result_resp.status_code == 402:
            raise_if_credits_http_error(402, result_resp.text)
        if result_resp.status_code >= 400:
            raise ValueError(
                f"Official FAL result HTTP {result_resp.status_code}: "
                f"{result_resp.text[:500]}"
            )
        data = result_resp.json()
        if not isinstance(data, dict):
            raise ValueError("Official FAL result returned non-object JSON")
        return data
