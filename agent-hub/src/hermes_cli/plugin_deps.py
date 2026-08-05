"""插件服务依赖图 + 拓扑排序 + 启动前校验（LT-006.02.02）.

数据来自 manifest 的 ``provides_services`` / ``requires_services``（设计 §6）。

规则（§9.1 / D7）：
- **仅 ``binding=ready`` 的边**约束加载顺序与环检测；``ready`` 环 → 报错。
- **``binding=lazy`` 边不约束顺序、允许成环**（相互引用正解）。
- 硬依赖（``optional=False``）若无任何插件 provider → 启动前 fail-fast。

本模块对 manifest **鸭子类型**（只读 ``.provides_services`` / ``.requires_services`` /
``.key`` / ``.name``），**不 import** ``plugins.py``，避免环。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_VALID_BINDINGS = frozenset({"lazy", "ready"})


@dataclass(frozen=True)
class RequiredService:
    """``requires_services`` 单条：契约 key + 硬/软 + 绑定时机."""

    key: str
    optional: bool = False
    binding: str = "lazy"  # lazy（默认，不约束序、允许成环）| ready（约束序、禁环）

    @staticmethod
    def parse(raw: Any) -> "RequiredService":
        """从 manifest YAML 的一条（dict 或裸字符串）解析."""
        if isinstance(raw, str):
            return RequiredService(key=raw)
        if isinstance(raw, dict):
            key = str(raw.get("key", "")).strip()
            if not key:
                raise ValueError(f"requires_services 条目缺 key: {raw!r}")
            binding = str(raw.get("binding", "lazy"))
            if binding not in _VALID_BINDINGS:
                raise ValueError(
                    f"requires_services[{key}].binding 非法: {binding!r}，须 lazy|ready"
                )
            return RequiredService(
                key=key, optional=bool(raw.get("optional", False)), binding=binding,
            )
        raise ValueError(f"requires_services 条目类型非法: {raw!r}")


class DependencyError(Exception):
    """依赖图基础异常."""


class MissingProviderError(DependencyError):
    """硬依赖无 provider（启动前 fail-fast）."""


class DependencyCycleError(DependencyError):
    """ready 边成环（提示改 lazy 或拆契约）."""


def _key(m: Any) -> str:
    return getattr(m, "key", "") or getattr(m, "name", "")


def provider_index(manifests: list[Any]) -> dict[str, list[str]]:
    """service key → 提供它的插件 key 列表."""
    idx: dict[str, list[str]] = {}
    for m in manifests:
        for s in getattr(m, "provides_services", []) or []:
            idx.setdefault(s, []).append(_key(m))
    return idx


def validate_providers(manifests: list[Any]) -> None:
    """硬依赖（optional=False）须有 provider，否则 MissingProviderError（fail-fast）."""
    idx = provider_index(manifests)
    missing: list[tuple[str, str]] = []
    for m in manifests:
        for req in getattr(m, "requires_services", []) or []:
            if not req.optional and req.key not in idx:
                missing.append((_key(m), req.key))
    if missing:
        detail = "; ".join(f"{p} 需要 {k}" for p, k in missing)
        raise MissingProviderError(f"硬依赖缺 provider（无插件 provide）: {detail}")


def resolve_load_order(manifests: list[Any]) -> list[Any]:
    """拓扑排序（仅 ready 边约束）；ready 环 → DependencyCycleError.

    返回排序后的 manifest 列表：provider 先于其 ready-consumer。lazy 边被忽略，
    故 lazy 相互引用不会触发环错误。**同层保持输入顺序**（向后兼容：无 ready 依赖的
    存量插件加载序 = 发现序，不被打乱）。
    """
    idx = provider_index(manifests)
    by_key = {_key(m): m for m in manifests}
    input_order = [_key(m) for m in manifests]
    # deps[consumer] = {该 consumer 经 ready 边依赖的 provider keys}
    deps: dict[str, set[str]] = {k: set() for k in by_key}
    for m in manifests:
        ck = _key(m)
        for req in getattr(m, "requires_services", []) or []:
            if req.binding != "ready":
                continue
            for pk in idx.get(req.key, []):
                if pk != ck:
                    deps[ck].add(pk)

    order: list[Any] = []
    remaining = {k: set(v) for k, v in deps.items()}
    while remaining:
        # 按输入顺序取"无未满足 ready 依赖"的节点（保序）
        ready_nodes = [k for k in input_order if k in remaining and not remaining[k]]
        if not ready_nodes:
            raise DependencyCycleError(
                "ready 边成环（改 binding:lazy 或拆契约）: "
                + ", ".join(sorted(remaining))
            )
        for k in ready_nodes:
            order.append(by_key[k])
            del remaining[k]
        for v in remaining.values():
            v.difference_update(ready_nodes)
    return order
