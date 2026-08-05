"""ClawBot / A-Main 标准 Gateway 会话 key（CR-133 不再使用固定 channel session）."""

from __future__ import annotations

from pathlib import Path

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.session import SessionSource, SessionStore


def _clawbot_dm_source(user_id: str = "wx_peer_001") -> SessionSource:
    return SessionSource(
        platform=Platform.CLAWBOT,
        chat_type="dm",
        user_id=user_id,
        chat_id=user_id,
    )


def test_clawbot_uses_profile_scoped_session_key(tmp_path: Path) -> None:
    cfg = GatewayConfig()
    cfg.platforms[Platform.CLAWBOT] = PlatformConfig(
        enabled=True,
        extra={"profile": "assistant"},
    )
    store = SessionStore(tmp_path / "sessions", cfg)
    key_a = store._generate_session_key(_clawbot_dm_source())
    key_b = store._generate_session_key(_clawbot_dm_source("wx_peer_002"))
    assert key_a == "agent:assistant:clawbot:dm:wx_peer_001"
    assert key_b == "agent:assistant:clawbot:dm:wx_peer_002"
    assert key_a != key_b


def test_clawbot_get_or_create_uses_generated_session_id(tmp_path: Path) -> None:
    cfg = GatewayConfig()
    cfg.platforms[Platform.CLAWBOT] = PlatformConfig(
        enabled=True,
        extra={"profile": "assistant"},
    )
    store = SessionStore(tmp_path / "sessions", cfg)
    entry = store.get_or_create_session(_clawbot_dm_source())
    assert entry.session_key == "agent:assistant:clawbot:dm:wx_peer_001"
    assert entry.session_id
    assert "_" in entry.session_id
