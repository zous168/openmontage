"""ClawBot / iLink 扫码绑定（同步 HTTP，供 Dashboard onboarding 轮询）."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from gateway.platforms.weixin import (
    EP_GET_BOT_QR,
    EP_GET_QR_STATUS,
    EP_SEND_MESSAGE,
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    ILINK_BASE_URL,
    ITEM_TEXT,
    MSG_STATE_FINISH,
    MSG_TYPE_BOT,
    _base_info,
    _headers,
    _json_dumps,
)

logger = logging.getLogger(__name__)

_MAX_QR_REFRESHES = 3
_DEFAULT_BOT_TYPE = "3"
BIND_SUCCESS_MESSAGE = (
    "✅ WeChat ClawBot 绑定成功！\n"
    "已连接您的微信，现在可以直接开始对话。"
)
CLAWBOT_TEST_MESSAGE = (
    "✅ ClawBot 通道测试\n"
    "收到此消息说明绑定与发信正常，可以直接开始对话。"
)
CLAWBOT_USER_MUST_MESSAGE_FIRST = (
    "请先在微信向 ClawBot 发送任意一条消息，建立会话后再试。"
)
ILINK_RET_USER_MUST_INITIATE = -2


def _ilink_get(base_url: str, endpoint: str, *, timeout: float = 35.0) -> dict[str, Any]:
    import httpx

    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"iLink GET {endpoint}: unexpected payload")
    return data


def fetch_ilink_qr(*, bot_type: str = _DEFAULT_BOT_TYPE, base_url: str = ILINK_BASE_URL) -> dict[str, str]:
    """请求 iLink 绑定二维码。返回 qrcode（轮询键）、qr_payload（扫码内容）。"""
    resp = _ilink_get(base_url, f"{EP_GET_BOT_QR}?bot_type={bot_type}")
    qrcode = str(resp.get("qrcode") or "").strip()
    qrcode_url = str(resp.get("qrcode_img_content") or resp.get("qrcode_url") or "").strip()
    if not qrcode:
        raise RuntimeError("iLink get_bot_qrcode: missing qrcode")
    qr_payload = qrcode_url if qrcode_url else qrcode
    return {"qrcode": qrcode, "qr_payload": qr_payload, "base_url": base_url}


def poll_ilink_qr_status(
    qrcode: str,
    *,
    base_url: str = ILINK_BASE_URL,
) -> dict[str, Any]:
    """轮询扫码状态。status: wait | scaned | scaned_but_redirect | expired | confirmed."""
    resp = _ilink_get(base_url, f"{EP_GET_QR_STATUS}?qrcode={qrcode}")
    status = str(resp.get("status") or "wait")
    return {
        "status": status,
        "base_url": str(resp.get("baseurl") or base_url).strip().rstrip("/") or base_url,
        "account_id": str(resp.get("ilink_bot_id") or "").strip(),
        "token": str(resp.get("bot_token") or "").strip(),
        "user_id": str(resp.get("ilink_user_id") or "").strip(),
        "redirect_host": str(resp.get("redirect_host") or "").strip(),
    }


def persist_ilink_bind(
    hermes_home: str,
    *,
    account_id: str,
    token: str,
    base_url: str,
    user_id: str,
) -> None:
    """[已废弃] 凭据 SSOT 为 ``config.yaml`` → ``platforms.clawbot``；不再写 ``weixin/accounts/``。"""
    del hermes_home, account_id, token, base_url, user_id


def send_ilink_text_message(
    *,
    token: str,
    base_url: str,
    to_user_id: str,
    text: str,
    context_token: str | None = None,
    timeout: float = 35.0,
) -> dict[str, Any]:
    """Send a one-shot text message via iLink (used after ClawBot QR bind)."""
    recipient = str(to_user_id or "").strip()
    body_text = str(text or "").strip()
    if not token or not recipient or not body_text:
        raise ValueError("send_ilink_text_message requires token, to_user_id, and text")

    message: dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": recipient,
        "client_id": f"clawbot-{uuid.uuid4().hex[:12]}",
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": body_text}}],
    }
    if context_token:
        message["context_token"] = context_token
    payload = {"msg": message, "base_info": _base_info()}
    body = _json_dumps(payload)
    url = f"{base_url.rstrip('/')}/{EP_SEND_MESSAGE}"

    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(url, content=body.encode("utf-8"), headers=_headers(token, body))
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("iLink sendmessage: unexpected payload")
    return data


def ilink_send_requires_user_initiate(
    result: dict[str, Any],
    *,
    has_context_token: bool,
) -> bool:
    """True when iLink ret=-2 means the user must DM the bot before proactive send."""
    from gateway.platforms.weixin import _is_stale_session_ret

    ret = result.get("ret", result.get("errcode"))
    errcode = result.get("errcode")
    errmsg = str(result.get("errmsg") or result.get("msg") or "").strip()
    if ret not in {ILINK_RET_USER_MUST_INITIATE, str(ILINK_RET_USER_MUST_INITIATE)} and errcode not in {
        ILINK_RET_USER_MUST_INITIATE,
        str(ILINK_RET_USER_MUST_INITIATE),
    }:
        return False
    if has_context_token and _is_stale_session_ret(ret, errcode, errmsg):
        return False
    # Without an active session, iLink -2 is "user must message the bot first".
    if not has_context_token:
        return True
    # With context_token, bare -2 is still treated as user-initiate for ClawBot UX.
    return not errmsg or errmsg.lower() == "unknown error"


def format_ilink_send_error(
    result: dict[str, Any],
    *,
    has_context_token: bool,
) -> str:
    if ilink_send_requires_user_initiate(result, has_context_token=has_context_token):
        return CLAWBOT_USER_MUST_MESSAGE_FIRST
    errmsg = str(result.get("errmsg") or result.get("msg") or "").strip()
    return errmsg or str(result)


def send_clawbot_bind_success_message(
    *,
    token: str,
    base_url: str,
    user_id: str,
    text: str = BIND_SUCCESS_MESSAGE,
) -> bool:
    """Notify the bound WeChat user; failures are logged and do not raise."""
    ok, _detail = send_clawbot_text_message(
        token=token,
        base_url=base_url,
        user_id=user_id,
        text=text,
        log_context="bind success",
    )
    return ok


def send_clawbot_text_message(
    *,
    token: str,
    base_url: str,
    user_id: str,
    text: str,
    account_id: str | None = None,
    log_context: str = "outbound",
) -> tuple[bool, str]:
    """Send text to bound WeChat user; returns (ok, detail for UI)."""
    import time

    from gateway.platforms.clawbot.storage import ClawbotContextTokenStore
    from gateway.platforms.weixin import _is_stale_session_ret
    from hermes_constants import get_hermes_home

    recipient = str(user_id or "").strip()
    if not token or not recipient:
        return False, "ClawBot credentials incomplete — rebind via QR code."

    context_token = None
    if account_id:
        context_token = ClawbotContextTokenStore(str(get_hermes_home())).get(account_id, recipient)

    last_detail = "send failed"
    for attempt in range(3):
        try:
            result = send_ilink_text_message(
                token=token,
                base_url=base_url,
                to_user_id=recipient,
                text=text,
                context_token=context_token,
            )
        except Exception as exc:
            logger.warning("ClawBot %s message failed: %s", log_context, exc)
            return False, str(exc)

        ret = result.get("ret", result.get("errcode"))
        errcode = result.get("errcode")
        if ret in {None, 0, "0"}:
            logger.info("ClawBot %s message sent to %s", log_context, recipient[:16])
            return True, "Message sent to your WeChat."

        errmsg = str(result.get("errmsg") or result.get("msg") or "").strip()
        if context_token and _is_stale_session_ret(ret, errcode, errmsg):
            context_token = None
            continue
        if ilink_send_requires_user_initiate(
            result, has_context_token=bool(context_token)
        ):
            return False, CLAWBOT_USER_MUST_MESSAGE_FIRST
        if ret in {ILINK_RET_USER_MUST_INITIATE, str(ILINK_RET_USER_MUST_INITIATE)} and attempt < 2:
            time.sleep(3)
            last_detail = errmsg or str(result)
            continue
        last_detail = format_ilink_send_error(
            result, has_context_token=bool(context_token)
        )
        logger.warning("ClawBot %s message rejected: %s", log_context, result)
        return False, last_detail

    return False, last_detail


def clawbot_has_peer_session(*, account_id: str | None, user_id: str) -> bool:
    """True when we have a peer context_token (user has DMed the bot at least once)."""
    from gateway.platforms.clawbot.storage import ClawbotContextTokenStore
    from hermes_constants import get_hermes_home

    recipient = str(user_id or "").strip()
    if not recipient:
        return False
    store = ClawbotContextTokenStore(str(get_hermes_home()))
    return bool(store.get(str(account_id or "").strip(), recipient))


def send_clawbot_test_message(
    *,
    token: str,
    base_url: str,
    user_id: str,
    account_id: str | None = None,
    text: str = CLAWBOT_TEST_MESSAGE,
) -> tuple[bool, str]:
    """Send channel test ping to the bound WeChat user.

    Requires an established peer session (context_token). iLink often returns
    ret=0 without a session while WeChat never delivers — treat that as failure.
    """
    if not clawbot_has_peer_session(account_id=account_id, user_id=user_id):
        return False, CLAWBOT_USER_MUST_MESSAGE_FIRST
    ok, detail = send_clawbot_text_message(
        token=token,
        base_url=base_url,
        user_id=user_id,
        account_id=account_id,
        text=text,
        log_context="test",
    )
    if ok:
        return True, "测试消息已发送到您的微信，请查收。"
    return False, detail
