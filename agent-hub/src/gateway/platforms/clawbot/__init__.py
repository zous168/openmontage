"""ClawBot 平台包（个人微信官方机器人）。

主适配器在 ``adapter.py``（原 ``clawbot.py``）；子模块 ``config`` / ``ilink`` /
``onboard``。re-export adapter 符号，使 ``from gateway.platforms.clawbot import X`` 不变。
"""

from gateway.platforms.clawbot.adapter import *  # noqa: F401,F403
