"""Device login orchestration (dev stub + control-server production path)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from dataclasses import replace

from core.platform.control_server import (
    ControlServerClient,
    ControlServerConfigError,
    ControlServerError,
    DeviceLoginResult,
    EntitlementExpiredError,
    InvalidCredentialsError,
)
from core.platform.device.device_fingerprint import get_device_os, get_hub_app_version
from core.platform.device.hub_identity import get_hub_product_code
from core.platform.device.device_id import get_or_create_device_id
from core.platform.device.local_device_auth import (
    DeviceAuth,
    LocalDeviceAuthStore,
    device_auth_store_lock,
    save_from_control_server,
)

_log = logging.getLogger(__name__)

REFRESH_THRESHOLD_SEC = 300.0
# 后台轮询：会话有效性 + 授权对齐；密码重置 / 到期后最迟约 1 分钟感知并停工。
REFRESH_POLL_INTERVAL_SEC = 60.0
REFRESH_FAILURE_COOLDOWN_SEC = 30.0
# 与 REFRESH_POLL 同频：GET /api/hub/me 既对齐模块，也探测 access 是否被吊销。
ENTITLEMENTS_POLL_INTERVAL_SEC = 60.0

_last_refresh_failure_at: float = 0.0
_last_entitlements_sync_at: float = 0.0

# 与客户端 GATED_CHANNEL_PROFILES / enabled_modules code 同口径
GATED_CHANNEL_PROFILES = frozenset(
    {"douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss"}
)


def is_profile_entitled(profile_id: str | None) -> bool:
    """渠道 profile 是否在当前设备账号授权内。

    - 非门禁 profile（assistant / default / …）→ 放行
    - 无本地设备会话（未登录）→ 放行（与客户端 enabled_modules=null 一致）
    - 已登录 → 严格按 ``enabled_modules`` 判断
    """
    pid = str(profile_id or "").strip()
    if not pid or pid not in GATED_CHANNEL_PROFILES:
        return True
    auth = LocalDeviceAuthStore().load()
    if auth is None:
        return True
    return pid in list(auth.enabled_modules or [])


def require_profile_entitled(profile_id: str | None) -> None:
    """未授权渠道抛 ValueError（供入队 / MCP 工具复用）。"""
    pid = str(profile_id or "").strip()
    if not is_profile_entitled(pid):
        raise ValueError(f"模块未授权，无法操作渠道 {pid}")


@contextlib.contextmanager
def _cross_process_refresh_lock():
    """多 Hub 进程共享 device_auth.json 时，避免并发 refresh 轮换竞态."""
    from runtime_paths import resolve_hub_data_dir_path

    lock_path = resolve_hub_data_dir_path() / "device" / "device_auth.refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


def perform_device_login(
    *,
    login_name: str | None = None,
    password: str,
) -> DeviceAuth:
    """Control-server device login; persists session on success."""
    name = (login_name or "").strip() or None
    device_id = get_or_create_device_id()
    client = ControlServerClient()
    result = client.device_login(
        password,
        login_name=name,
        product_id=get_hub_product_code(),
        device_id=device_id,
        app_version=get_hub_app_version(),
        device_os=get_device_os(),
    )
    resolved_name = name or str(result.user.get("login_name") or "").strip()
    auth = save_from_control_server(resolved_name, result, device_id=device_id)
    # 产品默认：登录成功后主模型切到系统内置（官方渠道就绪时）
    try:
        from hermes_cli.official_gateway_models import ensure_official_as_default_main_model

        ensure_official_as_default_main_model(force=True)
    except Exception:  # noqa: BLE001 — 默认模型写入失败不阻断登录
        _log.exception("device login: failed to set official default main model")
    return auth


def device_login_api_payload(auth: DeviceAuth) -> dict[str, object]:
    return {
        "user_id": auth.user_id,
        "login_name": auth.login_name,
        "display_name": auth.display_name or auth.login_name,
        "tenant_id": auth.tenant_id,
        "tenant_name": auth.tenant_name,
        "device_id": auth.device_id,
        "expires_at": int(auth.expires_at),
        "enabled_modules": list(auth.enabled_modules or []),
        "entitlement_expires_at": auth.entitlement_expires_at,
        "product_grant_count": auth.product_grant_count,
        "credit_balance": auth.credit_balance,
        "compute_point_tokens": auth.compute_point_tokens,
        "industry": auth.industry or "",
        "contact_name": auth.contact_name or "",
        "contact_email": auth.contact_email or "",
    }


def apply_refresh_tokens(auth: DeviceAuth, *, access_token: str, refresh_token: str, expires_in: int) -> DeviceAuth:
    updated = replace(
        auth,
        access_token=access_token,
        expires_at=time.time() + expires_in,
        refresh_token=refresh_token,
    )
    LocalDeviceAuthStore().save(updated)
    return updated


def _clear_device_auth_unlocked(*, reason: str) -> None:
    LocalDeviceAuthStore()._clear_unlocked()
    try:
        from hermes_cli.official_gateway_models import clear_official_gateway_models_cache

        clear_official_gateway_models_cache()
    except Exception:
        _log.debug("clear official models cache on logout failed", exc_info=True)
    try:
        from plugins.mxai.orchestrator.queue_manager import QueueManager

        QueueManager.get().fail_closed_disarm()
    except Exception:  # noqa: BLE001 — best-effort during auth teardown
        _log.exception("device auth fail-closed: queue disarm failed")
    _log.warning("device auth fail-closed: %s", reason)


def get_fresh_device_access_token() -> str:
    """返回当前设备 access JWT；临近过期时先 refresh。

    官方渠道（llm-gateway）调用前应走此函数，避免 15 分钟票过期后
    仍拿旧 token 打网关 → ``JWT expired`` / 401。
    """
    try:
        ensure_device_access_fresh()
    except Exception:  # noqa: BLE001 — refresh 失败时仍尝试用磁盘上的票
        _log.debug("ensure_device_access_fresh before jwt read failed", exc_info=True)
    auth = LocalDeviceAuthStore().load()
    if auth is None:
        return ""
    return (auth.access_token or "").strip()


def ensure_device_access_fresh() -> None:
    """Proactive refresh when access token is near expiry."""
    global _last_refresh_failure_at

    with device_auth_store_lock:
        store = LocalDeviceAuthStore()
        auth = store._load_unlocked()
        if auth is None or not auth.refresh_token:
            return
        remaining = auth.expires_at - time.time()
        if remaining > REFRESH_THRESHOLD_SEC:
            return
        if (
            _last_refresh_failure_at
            and remaining > 0
            and (time.time() - _last_refresh_failure_at) < REFRESH_FAILURE_COOLDOWN_SEC
        ):
            return

    with _cross_process_refresh_lock():
        with device_auth_store_lock:
            store = LocalDeviceAuthStore()
            auth = store._load_unlocked()
            if auth is None or not auth.refresh_token:
                return
            remaining = auth.expires_at - time.time()
            if remaining > REFRESH_THRESHOLD_SEC:
                return
            _log.info(
                "device auth refresh start login=%s expires_in_sec=%.0f",
                auth.login_name,
                remaining,
            )
            refresh_token_used = auth.refresh_token
            try:
                refreshed = ControlServerClient().refresh(refresh_token_used)
                updated = replace(
                    auth,
                    access_token=refreshed.access_token,
                    expires_at=time.time() + refreshed.expires_in,
                    refresh_token=refreshed.refresh_token,
                )
                store._save_unlocked(updated)
                _last_refresh_failure_at = 0.0
                _log.info(
                    "device auth refresh ok login=%s new_expires_in_sec=%s",
                    auth.login_name,
                    refreshed.expires_in,
                )
            except InvalidCredentialsError as exc:
                latest = store._load_unlocked()
                if latest is not None and latest.refresh_token != refresh_token_used:
                    _log.info(
                        "device auth refresh failure ignored: session replaced login=%s",
                        latest.login_name,
                    )
                    _last_refresh_failure_at = 0.0
                    return
                # 密码重置 / 会话吊销：立即 fail-closed，不再等 access JWT 自然过期
                _log.warning(
                    "device auth credentials invalid — logging out login=%s (%s)",
                    auth.login_name,
                    exc,
                )
                _clear_device_auth_unlocked(reason=f"refresh_failed: {exc}")
            except EntitlementExpiredError as exc:
                latest = store._load_unlocked()
                if latest is not None and latest.refresh_token != refresh_token_used:
                    _last_refresh_failure_at = 0.0
                    return
                _log.warning(
                    "device auth entitlement expired on refresh — logging out login=%s (%s)",
                    auth.login_name,
                    exc,
                )
                _clear_device_auth_unlocked(reason=f"entitlement_expired: {exc}")
            except ControlServerError as exc:
                _log.warning(
                    "device auth refresh transient error login=%s error=%s",
                    auth.login_name,
                    exc,
                )


def _parse_entitlement_expiry(raw: str | None) -> float | None:
    """ISO8601 → unix；无法解析返回 None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime, timezone

        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _entitlement_lapsed(*, expires_at: str | None, grant_count: int) -> bool:
    """无有效授权，或最早到期时间已过。"""
    if int(grant_count or 0) <= 0:
        return True
    ts = _parse_entitlement_expiry(expires_at)
    if ts is None:
        return False  # 长期有效
    return ts <= time.time()


def ensure_entitlements_fresh() -> None:
    """周期拉取 ``GET /api/hub/me``：对齐授权 + 探测会话是否被吊销。

    - 凭据失效（重置密码 / generation 递增）→ 立即清会话并停工
    - 授权到期或无有效产品授权 → **强制下线**（清设备会话 + fail-closed 停工）
    """
    global _last_entitlements_sync_at

    with device_auth_store_lock:
        store = LocalDeviceAuthStore()
        auth = store._load_unlocked()
        if auth is None or not auth.access_token:
            return
        now = time.time()
        if (
            _last_entitlements_sync_at
            and (now - _last_entitlements_sync_at) < ENTITLEMENTS_POLL_INTERVAL_SEC
        ):
            return
        access_token = auth.access_token

    try:
        me = ControlServerClient().get_me(access_token)
    except InvalidCredentialsError as exc:
        _log.warning("device session revoked on /me — logging out (%s)", exc)
        with device_auth_store_lock:
            _clear_device_auth_unlocked(reason=f"me_session_revoked: {exc}")
        return
    except (ControlServerConfigError, ControlServerError) as exc:
        _log.debug("device entitlements sync skipped: %s", exc)
        return

    lapsed = _entitlement_lapsed(
        expires_at=me.entitlement_expires_at,
        grant_count=me.product_grant_count,
    )
    if lapsed:
        _log.warning(
            "device entitlement lapsed — force logout grants=%s expires_at=%s",
            me.product_grant_count,
            me.entitlement_expires_at,
        )
        with device_auth_store_lock:
            _last_entitlements_sync_at = time.time()
            _clear_device_auth_unlocked(
                reason=(
                    f"entitlement_lapsed grants={me.product_grant_count} "
                    f"expires_at={me.entitlement_expires_at}"
                )
            )
        return

    modules = list(me.enabled_modules or [])
    display_name = str(me.display_name or "").strip()
    tenant_name = ""
    industry = ""
    contact_name = ""
    contact_email = ""
    if isinstance(me.tenant, dict):
        tenant_name = str(me.tenant.get("name") or "").strip()
        industry = str(me.tenant.get("industry") or "").strip()
        contact_name = str(me.tenant.get("contact_name") or "").strip()
        contact_email = str(me.tenant.get("contact_email") or "").strip()

    with device_auth_store_lock:
        store = LocalDeviceAuthStore()
        auth = store._load_unlocked()
        if auth is None:
            return
        _last_entitlements_sync_at = time.time()
        next_display = display_name or auth.display_name or auth.login_name
        next_tenant_name = tenant_name or auth.tenant_name
        next_industry = industry or auth.industry
        next_contact_name = contact_name or auth.contact_name
        next_contact_email = contact_email or auth.contact_email
        changed = (
            list(modules) != list(auth.enabled_modules)
            or me.entitlement_expires_at != auth.entitlement_expires_at
            or me.product_grant_count != auth.product_grant_count
            or me.credit_balance != auth.credit_balance
            or me.compute_point_tokens != auth.compute_point_tokens
            or next_display != (auth.display_name or auth.login_name)
            or next_tenant_name != auth.tenant_name
            or next_industry != (auth.industry or "")
            or next_contact_name != (auth.contact_name or "")
            or next_contact_email != (auth.contact_email or "")
        )
        if changed:
            store._save_unlocked(
                replace(
                    auth,
                    enabled_modules=modules,
                    entitlement_expires_at=me.entitlement_expires_at,
                    product_grant_count=me.product_grant_count,
                    credit_balance=me.credit_balance,
                    compute_point_tokens=me.compute_point_tokens,
                    display_name=next_display,
                    tenant_name=next_tenant_name,
                    industry=next_industry,
                    contact_name=next_contact_name,
                    contact_email=next_contact_email,
                )
            )
            _log.info(
                "device entitlements updated login=%s display=%s modules=%s expires_at=%s grants=%s credit=%s",
                auth.login_name,
                next_display,
                modules,
                me.entitlement_expires_at,
                me.product_grant_count,
                me.credit_balance,
            )


def clear_device_auth_fail_closed(*, reason: str) -> None:
    """Clear device session and disarm orchestrator (fail-closed)."""
    with device_auth_store_lock:
        _clear_device_auth_unlocked(reason=reason)


def handle_auth_failure(*, reason: str) -> None:
    clear_device_auth_fail_closed(reason=reason)


async def device_auth_refresh_background(cancel: asyncio.Event) -> None:
    """Periodic proactive refresh (complements request-driven ensure_device_access_fresh)."""
    while not cancel.is_set():
        try:
            await asyncio.to_thread(ensure_device_access_fresh)
        except Exception:  # noqa: BLE001 — keep background loop alive
            _log.exception("device auth periodic refresh error")
        try:
            await asyncio.to_thread(ensure_entitlements_fresh)
        except Exception:  # noqa: BLE001 — keep background loop alive
            _log.exception("device entitlements periodic sync error")
        try:
            await asyncio.wait_for(cancel.wait(), timeout=REFRESH_POLL_INTERVAL_SEC)
            break
        except asyncio.TimeoutError:
            continue
