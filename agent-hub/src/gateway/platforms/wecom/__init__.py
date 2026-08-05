"""企业微信 AI Bot 平台包。

主适配器在 ``adapter.py``（原 ``wecom.py``）；子模块 ``callback`` / ``config`` /
``crypto``。re-export adapter 符号，使 ``from gateway.platforms.wecom import X`` 不变。
"""

from gateway.platforms.wecom.adapter import *  # noqa: F401,F403
