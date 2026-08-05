"""Hub 安装包身份 — 登录上报 control-server。"""

from __future__ import annotations

# 与 cfg.products.code 一致；各产品发行包在源码中固定此值（非环境变量）。
HUB_PRODUCT_CODE = "mxai"


def get_hub_product_code() -> str:
    return HUB_PRODUCT_CODE
