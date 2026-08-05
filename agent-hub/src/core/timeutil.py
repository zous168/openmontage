"""时间口径统一工具（全项目约定：存储/传输用 UTC 带标记；展示层转北京）.

约定（与 docs 一致）：
- **存储 & API 传输**：一律 UTC，ISO8601 带时区标记（``+00:00``）。
- **业务日/周期**（"今天""本周"）：按北京时区（``Asia/Shanghai`` = UTC+8）计算边界，
  再换算成 UTC 去比对 UTC 存储的数据（不能用本机 localtime，否则非北京机器错）。
- **展示（前端/给用户看）**：由前端把 UTC 转北京 +8h 显示。

纯时间戳一律用 ``utc_now_iso()``；业务日边界用 ``beijing_*`` 系列。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    """当前 UTC 时间（带 tzinfo）。"""
    return datetime.now(timezone.utc)


def utc_now_iso(*, timespec: str = "seconds") -> str:
    """当前 UTC 的 ISO8601（带 ``+00:00`` 标记）——纯时间戳落库/传输统一用此。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat(timespec=timespec)


def beijing_now() -> datetime:
    """当前北京时间（带 +08:00 tzinfo）——仅用于业务日/周期边界计算。"""
    return datetime.now(BEIJING)


def beijing_today_str() -> str:
    """北京"今天"的日期串 ``YYYY-MM-DD``（业务日语义，非本机时区）。"""
    return beijing_now().strftime("%Y-%m-%d")


def beijing_date_of_utc_str(utc_str: str) -> str:
    """UTC 时间串（``datetime('now')`` 形如 'YYYY-MM-DD HH:MM:SS' 或 ISO）→ 北京日期 ``YYYY-MM-DD``。

    用于把 UTC 存储的时间列按"北京业务日"归类/过滤。解析失败返回空串。
    """
    try:
        s = str(utc_str or "").replace("T", " ")[:19]
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(BEIJING).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
