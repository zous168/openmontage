"""hub_identity — 安装包绑定的基座产品编码。"""

from __future__ import annotations

from core.platform.device.hub_identity import HUB_PRODUCT_CODE, get_hub_product_code


def test_get_hub_product_code() -> None:
    assert get_hub_product_code() == HUB_PRODUCT_CODE
    assert get_hub_product_code() == "mxai"
