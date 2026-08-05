"""LT-002.03.0/03.1：个微 sidecar 生命周期 + 可行性 spike."""

from plugins.mxai.rpa.wechat.sidecar import feasibility_spike, WechatSidecar


def test_sidecar_register_heartbeat() -> None:
    WechatSidecar.reset()
    sc = WechatSidecar.get()
    reg = sc.register("wechat")
    assert reg["registered"]
    hb = sc.heartbeat()
    assert hb["alive"]


def test_feasibility_spike() -> None:
    WechatSidecar.reset()
    result = feasibility_spike()
    assert result["feasible"] is True
    assert result["outbound"]["sent"]
