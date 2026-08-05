"""HTTP client for control-server hub auth (device login + refresh)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

_ENV_BASE_URL = "CONTROL_SERVER_BASE_URL"
_LOGIN_PATH = "/api/hub/auth/login"
_REFRESH_PATH = "/api/hub/auth/refresh"
_ME_PATH = "/api/hub/me"
_DEFAULT_TIMEOUT_SEC = 30.0


class ControlServerConfigError(Exception):
    """CONTROL_SERVER_BASE_URL is missing or empty."""


class ControlServerError(Exception):
    """Network failure, malformed response, or unexpected control-server error."""


class InvalidCredentialsError(Exception):
    """login_name/password rejected or session revoked by control-server."""


class EntitlementExpiredError(Exception):
    """产品授权已到期 / 无有效授权（control-server sub_code=entitlement_expired）。"""


@dataclass(frozen=True)
class DeviceLoginResult:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user: dict[str, Any]
    tenant: dict[str, Any] | None
    # 本 AI 员工的有效模块快照（module code = agent-client ProfileId），
    # 由 control-server 依产品授权算得；driver of 客户端渠道显隐。
    enabled_modules: list[str] = field(default_factory=list)
    # 授权有效期摘要：最早非空到期 ISO 串（None=长期或无授权）+ active 授权条数。
    entitlement_expires_at: str | None = None
    product_grant_count: int = 0
    # 商户算力点余额（浮点，与 CS NUMERIC(20,6) 对齐；1 点 = compute_point_tokens token）。
    credit_balance: float = 0.0
    compute_point_tokens: int = 100


@dataclass(frozen=True)
class DeviceRefreshResult:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user: dict[str, Any]


@dataclass(frozen=True)
class DeviceMeResult:
    """``GET /api/hub/me`` 的最小投影：授权模块 + 有效期 + tenant。"""

    enabled_modules: list[str]
    tenant: dict[str, Any] | None
    entitlement_expires_at: str | None = None
    product_grant_count: int = 0
    credit_balance: float = 0.0
    compute_point_tokens: int = 100
    display_name: str = ""


def _coerce_credit_balance(raw: Any) -> float:
    """将 CS ``credit_balance`` 规范为 float。

    JSON 浮点 / int、以及偶发的数字字符串均接受；bool / 非法 → 0。
    （旧实现 ``isinstance(..., int)`` 会把 ``999973.83`` 当成非法写成 0。）
    """
    if isinstance(raw, bool) or raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val == val else 0.0  # NaN → 0
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return 0.0
        try:
            val = float(s)
        except ValueError:
            return 0.0
        return val if val == val else 0.0
    return 0.0


def _resolve_base_url(base_url: str | None) -> str:
    raw = base_url if base_url is not None else os.environ.get(_ENV_BASE_URL, "")
    normalized = raw.strip().rstrip("/")
    if not normalized:
        raise ControlServerConfigError(
            f"{_ENV_BASE_URL} is not set or empty; configure the control-server base URL"
        )
    return normalized


def _parse_envelope(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise ControlServerError(
            f"control-server returned non-JSON response (HTTP {response.status_code})"
        ) from exc
    if not isinstance(body, dict):
        raise ControlServerError("control-server envelope is not a JSON object")
    return body


def _is_invalid_credentials(envelope: dict[str, Any]) -> bool:
    return envelope.get("sub_code") == "invalid_credentials"


def _is_session_revoked(envelope: dict[str, Any]) -> bool:
    return envelope.get("sub_code") in {
        "session_revoked",
        "token_expired",
        "session_generation_mismatch",
    }


def _is_entitlement_expired(envelope: dict[str, Any]) -> bool:
    return envelope.get("sub_code") == "entitlement_expired"


def _handle_auth_envelope(response: httpx.Response, envelope: dict[str, Any]) -> None:
    if _is_invalid_credentials(envelope):
        message = str(envelope.get("message") or "invalid credentials")
        raise InvalidCredentialsError(message)
    if _is_entitlement_expired(envelope):
        message = str(envelope.get("message") or "entitlement expired")
        raise EntitlementExpiredError(message)
    if _is_session_revoked(envelope):
        message = str(envelope.get("message") or "session revoked")
        raise InvalidCredentialsError(message)
    code = envelope.get("code")
    if response.status_code != 200 or code != 200:
        message = str(
            envelope.get("message") or f"unexpected response (HTTP {response.status_code})"
        )
        raise ControlServerError(message)


def _normalize_login_tenant(
    user: dict[str, Any],
    tenant: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize tenant from CS login payload.

    Production control-server may omit ``data.tenant`` and only put
    ``tenant_id`` on ``data.user`` — synthesize a tenant dict so downstream
    persistence and local_guard see a non-empty tenant_id.
    """
    if tenant is not None:
        return dict(tenant)
    tenant_id = str(user.get("tenant_id") or "").strip()
    if not tenant_id:
        return None
    name = str(user.get("tenant_name") or user.get("display_name") or "").strip()
    return {"id": tenant_id, "name": name}


def _extract_enabled_modules(tenant: dict[str, Any] | None) -> list[str]:
    """从 tenant 对象取 enabled_modules（module code 列表）；缺失/异型→[]。"""
    if not isinstance(tenant, dict):
        return []
    mods = tenant.get("enabled_modules")
    if not isinstance(mods, list):
        return []
    return [str(m) for m in mods if isinstance(m, str) and m]


def _extract_entitlement(tenant: dict[str, Any] | None) -> tuple[str | None, int]:
    """从 tenant 对象取授权有效期摘要 (expires_at ISO|None, grant_count)。"""
    if not isinstance(tenant, dict):
        return None, 0
    raw_expiry = tenant.get("entitlement_expires_at")
    expires_at = raw_expiry if isinstance(raw_expiry, str) and raw_expiry else None
    raw_count = tenant.get("product_grant_count")
    count = raw_count if isinstance(raw_count, int) and not isinstance(raw_count, bool) else 0
    return expires_at, count


def _extract_credit(tenant: dict[str, Any] | None) -> tuple[float, int]:
    """从 tenant 对象取算力点余额与换算常量 (balance, tokens_per_point)。"""
    if not isinstance(tenant, dict):
        return 0.0, 100
    balance = _coerce_credit_balance(tenant.get("credit_balance"))
    raw_tokens = tenant.get("compute_point_tokens")
    tokens = (
        raw_tokens
        if isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool) and raw_tokens > 0
        else 100
    )
    return balance, tokens


def _parse_login_data(data: Any) -> DeviceLoginResult:
    if not isinstance(data, dict):
        raise ControlServerError("login response data is not an object")
    missing = [
        key
        for key in ("access_token", "refresh_token", "expires_in", "token_type", "user")
        if key not in data
    ]
    if missing:
        raise ControlServerError(f"login response missing fields: {', '.join(missing)}")
    user = data["user"]
    if not isinstance(user, dict):
        raise ControlServerError("login response user is not an object")
    tenant_raw = data.get("tenant")
    if tenant_raw is not None and not isinstance(tenant_raw, dict):
        raise ControlServerError("login response tenant is not an object")
    tenant = _normalize_login_tenant(dict(user), tenant_raw)
    # enabled_modules 只挂在真实 tenant 上；synthesize 分支（仅 user.tenant_id）
    # 无模块信息，取 tenant_raw 更贴近原始响应。
    source_tenant = tenant_raw if isinstance(tenant_raw, dict) else tenant
    enabled_modules = _extract_enabled_modules(source_tenant)
    entitlement_expires_at, product_grant_count = _extract_entitlement(source_tenant)
    credit_balance, compute_point_tokens = _extract_credit(source_tenant)
    return DeviceLoginResult(
        access_token=str(data["access_token"]),
        refresh_token=str(data["refresh_token"]),
        expires_in=int(data["expires_in"]),
        token_type=str(data["token_type"]),
        user=dict(user),
        tenant=tenant,
        enabled_modules=enabled_modules,
        entitlement_expires_at=entitlement_expires_at,
        product_grant_count=product_grant_count,
        credit_balance=credit_balance,
        compute_point_tokens=compute_point_tokens,
    )


def _parse_refresh_data(data: Any) -> DeviceRefreshResult:
    if not isinstance(data, dict):
        raise ControlServerError("refresh response data is not an object")
    missing = [
        key
        for key in ("access_token", "refresh_token", "expires_in", "token_type", "user")
        if key not in data
    ]
    if missing:
        raise ControlServerError(f"refresh response missing fields: {', '.join(missing)}")
    user = data["user"]
    if not isinstance(user, dict):
        raise ControlServerError("refresh response user is not an object")
    return DeviceRefreshResult(
        access_token=str(data["access_token"]),
        refresh_token=str(data["refresh_token"]),
        expires_in=int(data["expires_in"]),
        token_type=str(data["token_type"]),
        user=dict(user),
    )


def _post_json(
    client: httpx.Client,
    url: str,
    body: dict[str, str],
) -> httpx.Response:
    try:
        return client.post(
            url,
            json=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except httpx.RequestError as exc:
        raise ControlServerError(f"control-server request failed: {exc}") from exc


def _get_json(
    client: httpx.Client,
    url: str,
    access_token: str,
) -> httpx.Response:
    try:
        return client.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
    except httpx.RequestError as exc:
        raise ControlServerError(f"control-server request failed: {exc}") from exc


class ControlServerClient:
    """Sync client for control-server hub device auth."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self._base_url = _resolve_base_url(base_url)
        self._http_client = http_client
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def device_login(
        self,
        password: str,
        *,
        login_name: str | None = None,
        product_id: str | None = None,
        device_id: str | None = None,
        app_version: str | None = None,
        device_os: str | None = None,
    ) -> DeviceLoginResult:
        url = f"{self._base_url}{_LOGIN_PATH}"
        body: dict[str, str] = {"password": password}
        if login_name:
            body["login_name"] = login_name
        if product_id:
            body["product_id"] = product_id
        if device_id is not None:
            body["device_id"] = device_id
        if app_version is not None:
            body["app_version"] = app_version
        if device_os is not None:
            body["device_os"] = device_os

        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=httpx.Timeout(self._timeout))
        try:
            response = _post_json(client, url, body)
        finally:
            if owns_client:
                client.close()

        envelope = _parse_envelope(response)
        _handle_auth_envelope(response, envelope)
        return _parse_login_data(envelope.get("data"))

    def refresh(self, refresh_token: str) -> DeviceRefreshResult:
        url = f"{self._base_url}{_REFRESH_PATH}"
        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=httpx.Timeout(self._timeout))
        try:
            response = _post_json(client, url, {"refresh_token": refresh_token})
        finally:
            if owns_client:
                client.close()

        envelope = _parse_envelope(response)
        _handle_auth_envelope(response, envelope)
        return _parse_refresh_data(envelope.get("data"))

    def get_me(self, access_token: str) -> DeviceMeResult:
        """拉取当前 AI 员工身份 + 最新授权模块（授权变更后的对齐入口）。"""
        url = f"{self._base_url}{_ME_PATH}"
        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=httpx.Timeout(self._timeout))
        try:
            response = _get_json(client, url, access_token)
        finally:
            if owns_client:
                client.close()

        envelope = _parse_envelope(response)
        _handle_auth_envelope(response, envelope)
        data = envelope.get("data")
        tenant = data.get("tenant") if isinstance(data, dict) else None
        if tenant is not None and not isinstance(tenant, dict):
            raise ControlServerError("me response tenant is not an object")
        entitlement_expires_at, product_grant_count = _extract_entitlement(tenant)
        credit_balance, compute_point_tokens = _extract_credit(tenant)
        display_name = ""
        if isinstance(data, dict):
            display_name = str(data.get("display_name") or "").strip()
        return DeviceMeResult(
            enabled_modules=_extract_enabled_modules(tenant),
            tenant=dict(tenant) if isinstance(tenant, dict) else None,
            entitlement_expires_at=entitlement_expires_at,
            product_grant_count=product_grant_count,
            credit_balance=credit_balance,
            compute_point_tokens=compute_point_tokens,
            display_name=display_name,
        )
