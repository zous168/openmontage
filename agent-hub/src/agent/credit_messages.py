"""官方算力渠道（llm-gateway）用户可见文案。"""

from __future__ import annotations

# Dashboard / FloatingChat 默认中文；勿用「请充值」掩盖 CS 余额与网关 Redis 运行余额不同步。
_OFFICIAL_CREDITS_INSUFFICIENT_ZH = (
    "官方模型通道暂时无法调用：网关侧运行余额不足。"
    "若账号详情仍显示有算力点，多半是商户余额与模型通道未同步，"
    "请联系管理员对齐网关运行余额后再试；也可在设置中改用自有 API Key 模型。"
)


def official_credits_insufficient_message(*, lang: str | None = None) -> str:
    """官方网关 402 / 算力不足；catalog 缺失时仍返回可读中文。

    ``lang="zh"``：Dashboard 助理等中文产品面强制中文，避免 ``display.language=en`` 漏出英文。
    """
    from agent.i18n import t

    if lang:
        msg = t("gateway.credits.insufficient", lang=lang)
        if msg == "gateway.credits.insufficient":
            return _OFFICIAL_CREDITS_INSUFFICIENT_ZH if lang == "zh" else msg
        return msg

    msg = t("gateway.credits.insufficient")
    if msg == "gateway.credits.insufficient":
        msg = t("gateway.credits.insufficient", lang="zh")
    if msg == "gateway.credits.insufficient":
        return _OFFICIAL_CREDITS_INSUFFICIENT_ZH
    return msg


def official_credits_insufficient_for_assistant(detail: str = "") -> str:
    """FloatingChat / mxai 助理：强制中文，并在本机仍显示有点时点明「未同步」。"""
    text = official_credits_insufficient_message(lang="zh")
    try:
        from core.platform.device.local_device_auth import LocalDeviceAuthStore

        auth = LocalDeviceAuthStore().load()
        bal = float(getattr(auth, "credit_balance", 0) or 0) if auth else 0.0
    except Exception:
        bal = 0.0
    if bal > 0:
        text = f"{text}（本机账号显示约 {bal:g} 点，与网关未同步）"
    # 网关原文里若带 balance=，便于排障（不替代主文案）
    raw = (detail or "").strip()
    if "balance=" in raw.lower() and "balance=" not in text.lower():
        # 仅截取短片段，避免整段英文堆进气泡
        lowered = raw.lower()
        idx = lowered.find("balance=")
        snippet = raw[idx : idx + 32].split(")")[0]
        if snippet:
            text = f"{text}[{snippet}]"
    return text
