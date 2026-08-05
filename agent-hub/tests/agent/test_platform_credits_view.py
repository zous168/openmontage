"""平台算力点 /credits 视图：设备登录优先于 Nous Portal。"""

from __future__ import annotations

from types import SimpleNamespace

from agent.account_usage import CreditsView, _build_platform_credits_view, build_credits_view


def test_platform_credits_view_from_device_auth(monkeypatch):
    auth = SimpleNamespace(
        access_token="jwt-token",
        credit_balance=1234,
        compute_point_tokens=100,
        tenant_name="演示商户",
        tenant_id="t-1",
        login_name="aw_seed_demo001",
    )

    class _Store:
        def load(self):
            return auth

    monkeypatch.setattr(
        "core.platform.device.local_device_auth.LocalDeviceAuthStore",
        _Store,
    )

    view = _build_platform_credits_view(markdown=True)
    assert view is not None
    assert view.logged_in is True
    assert view.source == "platform"
    assert view.depleted is False
    assert any("1,234" in line for line in view.balance_lines)
    assert view.identity_line and "演示商户" in view.identity_line


def test_build_credits_view_prefers_platform(monkeypatch):
    platform = CreditsView(
        logged_in=True,
        balance_lines=("余额：10 点",),
        identity_line="商户 / 账号：demo",
        source="platform",
    )
    monkeypatch.setattr(
        "agent.account_usage._build_platform_credits_view",
        lambda **_kwargs: platform,
    )

    def _boom(**_kwargs):
        raise AssertionError("must not fall through to Nous when platform is ready")

    monkeypatch.setattr(
        "hermes_cli.auth.get_provider_auth_state",
        _boom,
        raising=False,
    )

    view = build_credits_view(markdown=True)
    assert view.source == "platform"
    assert view.balance_lines == ("余额：10 点",)


def test_platform_credits_none_when_logged_out(monkeypatch):
    class _Store:
        def load(self):
            return None

    monkeypatch.setattr(
        "core.platform.device.local_device_auth.LocalDeviceAuthStore",
        _Store,
    )
    assert _build_platform_credits_view() is None
