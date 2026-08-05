"""设备登录态 — ``{HUB_DATA_DIR}/device/device_auth.json``."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.platform.control_server import DeviceLoginResult
from core.platform.control_server.client import _coerce_credit_balance

_log = logging.getLogger(__name__)

# 设备会话文件读写 + refresh 串行化，避免并发 save/refresh 导致瞬时读不到 tenant。
device_auth_store_lock = threading.RLock()


@dataclass
class DeviceAuth:
    user_id: str
    login_name: str
    tenant_id: str
    tenant_name: str
    device_id: str
    access_token: str
    expires_at: float
    refresh_token: str = ""
    # AI 员工展示名（control-server hub_users.display_name）；UI 欢迎语/顶栏用。
    display_name: str = ""
    # control-server 依产品授权算得的有效模块快照（module code = ProfileId）。
    # 客户端据此显隐渠道；登录写入、刷新保留、周期 get_me 对齐。
    enabled_modules: list[str] = field(default_factory=list)
    # 授权有效期摘要：最早非空到期 ISO 串（None=长期或无授权）+ active 授权条数。
    entitlement_expires_at: str | None = None
    product_grant_count: int = 0
    credit_balance: float = 0.0
    compute_point_tokens: int = 100
    # CS 商户资料（向导公司基础信息默认值；只读透传）
    industry: str = ""
    contact_name: str = ""
    contact_email: str = ""


def _auth_path() -> Path:
    from runtime_paths import resolve_hub_data_dir_path

    return resolve_hub_data_dir_path() / "device" / "device_auth.json"


class LocalDeviceAuthStore:
    """读写本机 ai_worker 设备会话（营销 API 注入 tenant 用）."""

    def load(self) -> DeviceAuth | None:
        with device_auth_store_lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> DeviceAuth | None:
        path = _auth_path()
        if not path.is_file():
            return None
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("device auth load failed path=%s error=%s", path, exc)
            return None
        access = str(raw.get("access_token") or "").strip()
        tenant_id = str(raw.get("tenant_id") or "").strip()
        if not access or not tenant_id:
            _log.warning(
                "device auth incomplete path=%s has_access=%s has_tenant=%s",
                path,
                bool(access),
                bool(tenant_id),
            )
            return None
        raw_modules = raw.get("enabled_modules")
        enabled_modules = (
            [str(m) for m in raw_modules if isinstance(m, str) and m]
            if isinstance(raw_modules, list)
            else []
        )
        raw_expiry = raw.get("entitlement_expires_at")
        entitlement_expires_at = (
            raw_expiry if isinstance(raw_expiry, str) and raw_expiry else None
        )
        raw_count = raw.get("product_grant_count")
        product_grant_count = (
            raw_count
            if isinstance(raw_count, int) and not isinstance(raw_count, bool)
            else 0
        )
        raw_credit = raw.get("credit_balance")
        credit_balance = _coerce_credit_balance(raw_credit)
        raw_tokens = raw.get("compute_point_tokens")
        compute_point_tokens = (
            raw_tokens
            if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool) and raw_tokens > 0
            else 100
        )
        login_name = str(raw.get("login_name") or "")
        display_name = str(raw.get("display_name") or "").strip() or login_name
        return DeviceAuth(
            user_id=str(raw.get("user_id") or ""),
            login_name=login_name,
            tenant_id=tenant_id,
            tenant_name=str(raw.get("tenant_name") or ""),
            device_id=str(raw.get("device_id") or ""),
            access_token=access,
            expires_at=float(raw.get("expires_at") or 0),
            refresh_token=str(raw.get("refresh_token") or ""),
            display_name=display_name,
            enabled_modules=enabled_modules,
            entitlement_expires_at=entitlement_expires_at,
            product_grant_count=product_grant_count,
            credit_balance=credit_balance,
            compute_point_tokens=compute_point_tokens,
            industry=str(raw.get("industry") or "").strip(),
            contact_name=str(raw.get("contact_name") or "").strip(),
            contact_email=str(raw.get("contact_email") or "").strip(),
        )

    def save(self, auth: DeviceAuth) -> None:
        with device_auth_store_lock:
            self._save_unlocked(auth)

    def _save_unlocked(self, auth: DeviceAuth) -> None:
        path = _auth_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "user_id": auth.user_id,
                    "login_name": auth.login_name,
                    "display_name": auth.display_name or auth.login_name,
                    "tenant_id": auth.tenant_id,
                    "tenant_name": auth.tenant_name,
                    "device_id": auth.device_id,
                    "access_token": auth.access_token,
                    "expires_at": auth.expires_at,
                    "refresh_token": auth.refresh_token,
                    "enabled_modules": list(auth.enabled_modules or []),
                    "entitlement_expires_at": auth.entitlement_expires_at,
                    "product_grant_count": auth.product_grant_count,
                    "credit_balance": auth.credit_balance,
                    "compute_point_tokens": auth.compute_point_tokens,
                    "industry": auth.industry or "",
                    "contact_name": auth.contact_name or "",
                    "contact_email": auth.contact_email or "",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def clear(self) -> None:
        with device_auth_store_lock:
            self._clear_unlocked()

    def _clear_unlocked(self) -> None:
        path = _auth_path()
        if path.is_file():
            path.unlink(missing_ok=True)
            _log.warning("device auth file removed path=%s", path)

    @property
    def tenant_id(self) -> str | None:
        auth = self.load()
        return auth.tenant_id if auth else None


def save_from_control_server(
    login_name: str,
    result: DeviceLoginResult,
    *,
    device_id: str,
) -> DeviceAuth:
    """Persist device session from control-server login response."""
    tenant = result.tenant or {}
    tenant_id = str(tenant.get("id") or result.user.get("tenant_id") or "").strip()
    tenant_name = str(
        tenant.get("name")
        or result.user.get("tenant_name")
        or result.user.get("display_name")
        or ""
    ).strip()
    display_name = str(result.user.get("display_name") or "").strip() or login_name
    tenant_industry = str(tenant.get("industry") or "").strip()
    tenant_contact_name = str(tenant.get("contact_name") or "").strip()
    tenant_contact_email = str(tenant.get("contact_email") or "").strip()
    auth = DeviceAuth(
        user_id=str(result.user.get("id") or ""),
        login_name=login_name,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        device_id=device_id,
        access_token=result.access_token,
        expires_at=time.time() + result.expires_in,
        refresh_token=result.refresh_token,
        display_name=display_name,
        enabled_modules=list(result.enabled_modules or []),
        entitlement_expires_at=result.entitlement_expires_at,
        product_grant_count=result.product_grant_count,
        credit_balance=result.credit_balance,
        compute_point_tokens=result.compute_point_tokens,
        industry=tenant_industry,
        contact_name=tenant_contact_name,
        contact_email=tenant_contact_email,
    )
    LocalDeviceAuthStore().save(auth)
    return auth
