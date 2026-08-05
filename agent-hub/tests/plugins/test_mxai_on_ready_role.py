"""mxai on_ready：Gateway 不启任何 Hub 副作用（含 config/migrations）."""

from __future__ import annotations

from unittest.mock import MagicMock

import plugins.mxai as mxai_mod


def test_on_ready_gateway_is_noop(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.process_role.is_gateway_process",
        lambda: True,
    )
    calls: list[str] = []

    def _track(name: str):
        def _fn(*_a, **_k):
            calls.append(name)
            raise AssertionError(f"gateway must not call {name}")

        return _fn

    monkeypatch.setattr(
        "plugins.mxai.cfg.domains.ensure_config_runtime",
        _track("ensure_config_runtime"),
        raising=False,
    )
    monkeypatch.setattr(
        mxai_mod,
        "ensure_runtime_bootstrap",
        _track("ensure_runtime_bootstrap"),
    )

    ctx = MagicMock()
    mxai_mod.on_ready(ctx)
    assert calls == []
    ctx.register_routes.assert_not_called()
