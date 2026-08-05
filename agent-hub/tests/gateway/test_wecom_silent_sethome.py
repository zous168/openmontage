"""企微首条私聊应静默写入 home channel，不向用户刷 /sethome 英文提示。"""

from __future__ import annotations

from gateway.config import HomeChannel, Platform
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def test_silent_auto_set_home_channel_wecom(monkeypatch) -> None:
    saved: dict[str, str] = {}

    def _save(key, value):
        saved[key] = str(value)
        monkeypatch.setenv(key, str(value))

    monkeypatch.setattr("hermes_cli.config.save_env_value", _save)

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = type("Cfg", (), {"platforms": {}})()

    source = SessionSource(
        platform=Platform.WECOM,
        chat_id="wmXXXX",
        chat_name="老板",
    )
    runner._silent_auto_set_home_channel(source, "WECOM_HOME_CHANNEL")

    assert saved.get("WECOM_HOME_CHANNEL") == "wmXXXX"
    home = runner.config.platforms[Platform.WECOM].home_channel
    assert isinstance(home, HomeChannel)
    assert home.chat_id == "wmXXXX"
