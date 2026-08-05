"""WeChat ClawBot Gateway 平台适配器（腾讯 iLink Bot API，复用 Weixin 实现）."""

from __future__ import annotations

import os
from typing import Any, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, SendResult
from gateway.platforms.clawbot.config import load_clawbot_config
from gateway.platforms.clawbot.outbound_queue import ClawbotOutboundQueue
from gateway.platforms.weixin import WeixinAdapter, check_weixin_requirements


def check_clawbot_requirements() -> bool:
    return check_weixin_requirements()


def _queue_min_interval_seconds(extra: dict[str, Any]) -> float:
    raw = extra.get("outbound_min_interval_seconds")
    if raw is None:
        raw = os.getenv("CLAWBOT_OUTBOUND_MIN_INTERVAL_SECONDS", "2.0")
    return max(0.0, float(raw))


def _queue_enabled(extra: dict[str, Any]) -> bool:
    if "outbound_queue_enabled" in extra:
        return bool(extra.get("outbound_queue_enabled"))
    return os.getenv("CLAWBOT_OUTBOUND_QUEUE_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class ClawbotAdapter(WeixinAdapter):
    """个人微信 ClawBot 通道：底层与 ``weixin`` 相同 iLink API，独立 ``platforms.clawbot`` 配置."""

    def __init__(self, config: PlatformConfig):
        ssot = load_clawbot_config()
        extra = dict(config.extra or {})
        token = str(
            config.token or extra.get("token") or ssot.get("token") or ""
        ).strip()
        account_id = str(extra.get("account_id") or ssot.get("account_id") or "").strip()
        base_url = str(extra.get("base_url") or ssot.get("base_url") or "").strip()
        user_id = str(
            extra.get("user_id")
            or extra.get("bound_wxid")
            or ssot.get("user_id")
            or ssot.get("bound_wxid")
            or ""
        ).strip()
        mapped = PlatformConfig(
            enabled=config.enabled,
            token=token or None,
            api_key=config.api_key,
            home_channel=config.home_channel,
            reply_to_mode=config.reply_to_mode,
            gateway_restart_notification=config.gateway_restart_notification,
            extra={
                **extra,
                "bind_status": bool(extra.get("bind_status") or ssot.get("bind_status")),
                "account_id": account_id,
                "token": token,
                "base_url": base_url,
                "user_id": user_id,
            },
        )
        super().__init__(mapped, platform=Platform.CLAWBOT)
        self._outbound_queue_enabled = _queue_enabled(mapped.extra)
        self._outbound_queue = ClawbotOutboundQueue(
            min_interval_seconds=_queue_min_interval_seconds(mapped.extra),
            name="clawbot-outbound",
        )
        if self._outbound_queue_enabled:
            self._defer_rate_limit_to_queue = True

    def _text_batch_key(self, event: MessageEvent) -> str:
        return self._session_key_for_event(event)

    async def connect(self) -> bool:
        connected = await super().connect()
        if connected and self._outbound_queue_enabled:
            await self._outbound_queue.start()
        return connected

    async def disconnect(self) -> None:
        if self._outbound_queue_enabled:
            await self._outbound_queue.stop()
        await super().disconnect()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        if not self._outbound_queue_enabled:
            return await super().send(
                chat_id,
                content,
                reply_to=reply_to,
                metadata=metadata,
            )
        if not self._send_session or not self._token:
            return SendResult(success=False, error="Not connected")

        async def _deliver() -> SendResult:
            return await self._deliver_outbound(
                chat_id,
                content,
                reply_to=reply_to,
                metadata=metadata,
            )

        return await self._outbound_queue.enqueue(_deliver, chat_id=chat_id)
