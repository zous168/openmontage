"""ClawBot 扫码绑定（腾讯 iLink Bot API · 与 weixin 适配器共用凭据存储）."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from gateway.platforms.clawbot.config import (
    clear_clawbot_credentials,
    clawbot_credentials_ready,
    load_clawbot_config,
    patch_clawbot_config,
)
from gateway.platforms.clawbot.ilink import (
    fetch_ilink_qr,
    poll_ilink_qr_status,
    send_clawbot_bind_success_message,
)
from gateway.platforms.weixin import ILINK_BASE_URL, check_weixin_requirements

logger = logging.getLogger(__name__)

_BIND_TTL_SECONDS = 480
_MXAI_MOCK_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _mxai_mock_enabled() -> bool:
    """与 ``plugins.mxai.runtime.mock.is_mxai_mock`` 同口径（全系统仅 ``MXAI_MOCK``）."""
    raw = (os.getenv("MXAI_MOCK") or "").strip().lower()
    return raw in _MXAI_MOCK_TRUTHY


def _session_expired(session: dict[str, Any]) -> bool:
    started = float(session.get("started_at") or 0)
    return bool(started and time.time() - started > _BIND_TTL_SECONDS)


def start_clawbot_bind() -> dict[str, Any]:
    # 首次绑定与「重新绑定」均先清旧凭据。否则 status 轮询见 credentials_ready
    # 会立刻 confirmed，二维码只闪一下就提示成功（用户尚未扫码）。
    clear_clawbot_credentials()
    if _mxai_mock_enabled():
        return _start_mock_bind()
    if not check_weixin_requirements():
        raise RuntimeError("ClawBot requires aiohttp and cryptography (Hermes messaging extras)")

    qr = fetch_ilink_qr()
    session = {
        "token": qr["qrcode"],
        "qr_payload": qr["qr_payload"],
        "status": "pending",
        "started_at": time.time(),
        "base_url": qr.get("base_url") or ILINK_BASE_URL,
        "refresh_count": 0,
        "qr_hint": "请使用手机微信扫一扫完成 ClawBot 绑定",
    }
    patch_clawbot_config({"bind_session": session})
    return {
        "bind_token": session["token"],
        "qr_payload": session["qr_payload"],
        "qr_hint": session["qr_hint"],
    }


def _start_mock_bind() -> dict[str, Any]:
    import uuid

    token = f"qr_{uuid.uuid4().hex[:12]}"
    session = {
        "token": token,
        "qr_payload": token,
        "status": "pending",
        "started_at": time.time(),
        "base_url": ILINK_BASE_URL,
        "refresh_count": 0,
        "qr_hint": "请使用微信扫描 ClawBot 绑定码（MXAI_MOCK）",
        "mock": True,
    }
    patch_clawbot_config({"bind_session": session})
    return {
        "bind_token": token,
        "qr_payload": token,
        "qr_hint": session["qr_hint"],
    }


def _mark_clawbot_bind_ready() -> None:
    try:
        from gateway.platform_connect_nudge import write_platform_connect_nudge

        write_platform_connect_nudge("clawbot")
    except Exception:
        logger.debug("Failed to nudge clawbot live connect after bind", exc_info=True)


def _confirm_mock_bind(session: dict[str, Any]) -> dict[str, Any]:
    wxid = f"wxid_claw_{hash(str(session.get('token'))) % 9000 + 1000}"
    cfg = patch_clawbot_config(
        {
            "enabled": True,
            "bind_status": True,
            "bound_wxid": wxid,
            "account_id": f"mock_{wxid}",
            "token": f"mock_token_{session.get('token', '')[:8]}",
            "base_url": ILINK_BASE_URL,
            "user_id": wxid,
            "stats": {"received": 0, "replied": 0, "today": 0},
            "bind_session": {**session, "status": "confirmed"},
        }
    )
    _mark_clawbot_bind_ready()
    return cfg


def _confirm_ilink_bind(session: dict[str, Any], poll: dict[str, Any]) -> dict[str, Any]:
    account_id = poll["account_id"]
    token = poll["token"]
    base_url = poll["base_url"]
    user_id = poll["user_id"]
    if not account_id or not token:
        raise RuntimeError("iLink bind confirmed but credentials were incomplete")

    bound_label = user_id or account_id
    cfg = patch_clawbot_config(
        {
            "enabled": True,
            "bind_status": True,
            "bound_wxid": bound_label,
            "account_id": account_id,
            "token": token,
            "base_url": base_url,
            "user_id": user_id,
            "stats": {"received": 0, "replied": 0, "today": 0},
            "bind_session": {**session, "status": "confirmed"},
        }
    )
    _mark_clawbot_bind_ready()
    if user_id and not _mxai_mock_enabled():
        send_clawbot_bind_success_message(token=token, base_url=base_url, user_id=user_id)
    return cfg


def _refresh_bind_qr(session: dict[str, Any]) -> dict[str, Any]:
    refresh_count = int(session.get("refresh_count") or 0) + 1
    if refresh_count > 3:
        session = {**session, "status": "expired"}
        patch_clawbot_config({"bind_session": session})
        return session
    qr = fetch_ilink_qr(base_url=str(session.get("base_url") or ILINK_BASE_URL))
    session = {
        **session,
        "token": qr["qrcode"],
        "qr_payload": qr["qr_payload"],
        "status": "pending",
        "started_at": time.time(),
        "base_url": qr.get("base_url") or session.get("base_url") or ILINK_BASE_URL,
        "refresh_count": refresh_count,
    }
    patch_clawbot_config({"bind_session": session})
    return session


def clawbot_bind_status(token: str) -> dict[str, Any]:
    cfg = load_clawbot_config()
    session = cfg.get("bind_session") or {}
    if session.get("token") != token:
        return {"status": "invalid", "bind_token": token}

    # 仅当本会话已 confirmed 才秒回成功；不得因「旧凭据仍在」短路，
    # 否则重新绑定会跳过扫码（pending 会话 + credentials_ready → 假成功）。
    if session.get("status") == "confirmed":
        return {
            "status": "confirmed",
            "bind_token": token,
            "bound": bool(clawbot_credentials_ready(cfg)),
            "qr_hint": session.get("qr_hint"),
            "qr_payload": session.get("qr_payload"),
        }

    if _session_expired(session):
        session = {**session, "status": "expired"}
        patch_clawbot_config({"bind_session": session})
        return {
            "status": "expired",
            "bind_token": token,
            "bound": False,
            "qr_hint": "绑定会话已过期，请重新发起扫码",
        }

    if session.get("mock"):
        started = float(session.get("started_at") or 0)
        if started and time.time() - started >= 1.2:
            cfg = _confirm_mock_bind(session)
            session = cfg.get("bind_session") or {}
        return {
            "status": session.get("status") or "pending",
            "bind_token": token,
            "bound": bool(cfg.get("bind_status")),
            "qr_hint": session.get("qr_hint"),
            "qr_payload": session.get("qr_payload"),
        }

    try:
        poll = poll_ilink_qr_status(token, base_url=str(session.get("base_url") or ILINK_BASE_URL))
    except Exception as exc:
        logger.warning("ClawBot QR poll failed: %s", exc)
        return {
            "status": "pending",
            "bind_token": token,
            "bound": False,
            "qr_hint": session.get("qr_hint"),
            "qr_payload": session.get("qr_payload"),
            "error": str(exc),
        }

    status = poll["status"]
    if status in {"wait", "scaned"}:
        hint = "已扫码，请在微信中确认…" if status == "scaned" else session.get("qr_hint")
        return {
            "status": "pending",
            "bind_token": token,
            "bound": False,
            "qr_hint": hint,
            "qr_payload": session.get("qr_payload"),
        }

    if status == "scaned_but_redirect" and poll.get("redirect_host"):
        session = {
            **session,
            "base_url": f"https://{poll['redirect_host']}",
        }
        patch_clawbot_config({"bind_session": session})

    if status == "expired":
        session = _refresh_bind_qr(session)
        if session.get("status") == "expired":
            return {
                "status": "expired",
                "bind_token": token,
                "bound": False,
                "qr_hint": "二维码已过期，请重新发起绑定",
            }
        return {
            "status": "pending",
            "bind_token": session["token"],
            "bound": False,
            "qr_hint": session.get("qr_hint"),
            "qr_payload": session.get("qr_payload"),
            "refreshed": True,
        }

    if status == "confirmed":
        cfg = _confirm_ilink_bind(session, poll)
        session = cfg.get("bind_session") or {}
        return {
            "status": "confirmed",
            "bind_token": token,
            "bound": True,
            "qr_hint": session.get("qr_hint"),
            "qr_payload": session.get("qr_payload"),
        }

    return {
        "status": "pending",
        "bind_token": token,
        "bound": False,
        "qr_hint": session.get("qr_hint"),
        "qr_payload": session.get("qr_payload"),
    }
