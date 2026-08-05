"""ClawBot Gateway 平台配置（``config.yaml`` → ``platforms.clawbot``）."""

from __future__ import annotations

from typing import Any


def _platform_block(config: dict[str, Any]) -> dict[str, Any]:
    platforms = config.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        config["platforms"] = platforms
    block = platforms.setdefault("clawbot", {})
    if not isinstance(block, dict):
        block = {}
        platforms["clawbot"] = block
    extra = block.setdefault("extra", {})
    if not isinstance(extra, dict):
        extra = {}
        block["extra"] = extra
    # CR-133：clawbot = 标准消息通道，恒绑 assistant profile（gateway 标准派发）
    extra.setdefault("profile", "assistant")
    return block


def clawbot_credentials_ready(cfg: dict[str, Any] | None = None) -> bool:
    """True when QR bind finished and bot ``token`` + ``account_id`` are persisted."""
    data = cfg if cfg is not None else load_clawbot_config()
    return bool(
        data.get("bind_status")
        and str(data.get("token") or "").strip()
        and str(data.get("account_id") or "").strip()
    )


def load_clawbot_config() -> dict[str, Any]:
    """读取 ClawBot 通道配置（Gateway SSOT）."""
    try:
        from hermes_cli.config import load_config

        plat = (load_config().get("platforms") or {}).get("clawbot") or {}
        if not isinstance(plat, dict):
            plat = {}
        extra = plat.get("extra") if isinstance(plat.get("extra"), dict) else {}
        stats = extra.get("stats") if isinstance(extra.get("stats"), dict) else {}
        return {
            "enabled": bool(plat.get("enabled")),
            "bind_status": bool(extra.get("bind_status")),
            "bound_wxid": str(extra.get("bound_wxid") or extra.get("user_id") or ""),
            "account_id": str(extra.get("account_id") or ""),
            "token": str(plat.get("token") or extra.get("token") or ""),
            "base_url": str(extra.get("base_url") or ""),
            "user_id": str(extra.get("user_id") or ""),
            "get_updates_buf": str(extra.get("get_updates_buf") or ""),
            "bind_session": extra.get("bind_session"),
            "stats": {
                "received": int(stats.get("received") or 0),
                "replied": int(stats.get("replied") or 0),
                "today": int(stats.get("today") or 0),
            },
        }
    except Exception:
        return {
            "enabled": False,
            "bind_status": False,
            "bound_wxid": "",
            "account_id": "",
            "token": "",
            "base_url": "",
            "user_id": "",
            "get_updates_buf": "",
            "bind_session": None,
            "stats": {"received": 0, "replied": 0, "today": 0},
        }


def clear_clawbot_credentials() -> dict[str, Any]:
    """Drop stale bot credentials while keeping channel enabled/disabled as-is."""
    from hermes_cli.config import load_config, save_config

    config = load_config()
    block = _platform_block(config)
    extra = block["extra"]
    # 重绑前清掉旧 peer 会话，避免测试/主动发信用过期 context_token 假成功。
    stale_peer = str(extra.get("user_id") or extra.get("bound_wxid") or "").strip()
    if stale_peer:
        try:
            from gateway.channel_directory import patch_platform_channel_fields

            patch_platform_channel_fields("clawbot", stale_peer, context_token="")
        except Exception:
            pass
    for key in ("token", "account_id", "bound_wxid", "user_id", "base_url"):
        extra.pop(key, None)
    block.pop("token", None)
    extra["bind_status"] = False
    extra["profile"] = "assistant"  # CR-133：标准通道恒绑 assistant profile
    save_config(config)
    return load_clawbot_config()


def patch_clawbot_config(patch: dict[str, Any]) -> dict[str, Any]:
    """合并写入 ClawBot 配置并持久化到 ``config.yaml``."""
    from hermes_cli.config import load_config, save_config

    config = load_config()
    block = _platform_block(config)
    extra = block["extra"]
    current = load_clawbot_config()

    if "enabled" in patch and patch["enabled"] is not None:
        block["enabled"] = bool(patch["enabled"])
        current["enabled"] = block["enabled"]
    if "token" in patch:
        token_val = str(patch.get("token") or "").strip()
        if token_val:
            block["token"] = token_val
            extra["token"] = token_val
            current["token"] = token_val
        else:
            block.pop("token", None)
            extra.pop("token", None)
            current["token"] = ""
    for key in (
        "bind_status",
        "bound_wxid",
        "bind_session",
        "account_id",
        "base_url",
        "user_id",
        "get_updates_buf",
    ):
        if key in patch and patch[key] is not None:
            if key in {"bound_wxid", "account_id", "user_id", "base_url", "get_updates_buf"} and patch[key] == "":
                extra.pop(key, None)
                current[key] = ""
            else:
                extra[key] = patch[key]
                current[key] = patch[key]
    if "stats" in patch and isinstance(patch["stats"], dict):
        extra["stats"] = patch["stats"]
        current["stats"] = patch["stats"]

    # CR-133：clawbot 作为标准消息通道，绑定 assistant profile（gateway 标准派发）。
    extra["profile"] = "assistant"

    save_config(config)
    return current


def load_clawbot_sync_buf() -> str:
    """iLink ``getUpdates`` 增量游标（账号级，存 ``config.yaml`` → ``platforms.clawbot.extra``）。"""
    return str(load_clawbot_config().get("get_updates_buf") or "")


def save_clawbot_sync_buf(sync_buf: str) -> None:
    """持久化 poll 游标到 ``config.yaml``（仅 patch clawbot 块）。"""
    patch_clawbot_config({"get_updates_buf": str(sync_buf or "")})
