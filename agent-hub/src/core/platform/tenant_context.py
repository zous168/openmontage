"""请求级营销租户 ContextVar（受保护 ``/api/*`` 注入）."""

from __future__ import annotations

from contextvars import ContextVar

current_tenant_id_var: ContextVar[str | None] = ContextVar(
    "current_tenant_id",
    default=None,
)
