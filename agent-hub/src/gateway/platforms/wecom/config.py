"""企微 AI Bot Gateway 配置（WebSocket 出站，无需公网回调）."""

from __future__ import annotations

from typing import Any

_DEFAULT_WELCOME = "您好！很高兴为您服务，请问有什么可以帮您？"


def _platform_block(config: dict[str, Any]) -> dict[str, Any]:
    platforms = config.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        config["platforms"] = platforms
    block = platforms.setdefault("wecom", {})
    if not isinstance(block, dict):
        block = {}
        platforms["wecom"] = block
    extra = block.setdefault("extra", {})
    if not isinstance(extra, dict):
        extra = {}
        block["extra"] = extra
    # CR-133：wecom = 标准消息通道，恒绑 assistant profile（gateway 标准派发）
    extra.setdefault("profile", "assistant")
    return block


def load_wecom_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config, load_env

        plat = (load_config().get("platforms") or {}).get("wecom") or {}
        if not isinstance(plat, dict):
            plat = {}
        extra = plat.get("extra") if isinstance(plat.get("extra"), dict) else {}
        env = load_env()
        return {
            "bot_id": extra.get("bot_id") or env.get("WECOM_BOT_ID", ""),
            "secret": extra.get("secret") or env.get("WECOM_SECRET", ""),
            "websocket_url": extra.get("websocket_url") or env.get("WECOM_WEBSOCKET_URL", ""),
            "welcome": extra.get("welcome_message") or extra.get("welcome") or _DEFAULT_WELCOME,
            "enabled": bool(plat.get("enabled")),
        }
    except Exception:
        return {
            "bot_id": "",
            "secret": "",
            "websocket_url": "",
            "welcome": _DEFAULT_WELCOME,
            "enabled": False,
        }


def patch_wecom_config(patch: dict[str, Any]) -> dict[str, Any]:
    from hermes_cli.config import load_config, save_config, save_env_value

    config = load_config()
    block = _platform_block(config)
    extra = block["extra"]
    current = load_wecom_config()

    if "enabled" in patch and patch["enabled"] is not None:
        block["enabled"] = bool(patch["enabled"])
        current["enabled"] = block["enabled"]

    field_map = {
        "bot_id": ("bot_id", "WECOM_BOT_ID"),
        "secret": ("secret", "WECOM_SECRET"),
        "websocket_url": ("websocket_url", "WECOM_WEBSOCKET_URL"),
    }
    for src, (extra_key, env_key) in field_map.items():
        if src in patch and patch[src] is not None:
            value = str(patch[src])
            extra[extra_key] = value
            current[src] = value
            if value.strip():
                save_env_value(env_key, value.strip())
    if "welcome" in patch and patch["welcome"] is not None:
        extra["welcome_message"] = str(patch["welcome"])
        current["welcome"] = extra["welcome_message"]

    save_config(config)
    return current
