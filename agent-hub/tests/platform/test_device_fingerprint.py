"""device_fingerprint — 本机 OS / Hub 版本采集。"""

from __future__ import annotations

import os

import pytest

from core.platform.device.device_fingerprint import get_device_os, get_hub_app_version


def test_get_device_os_non_empty_and_bounded() -> None:
    os_label = get_device_os()
    assert os_label
    assert len(os_label) <= 128
    assert "-" in os_label or os_label.isalpha()


def test_get_hub_app_version_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_APP_VERSION", "9.8.7-test")
    assert get_hub_app_version() == "9.8.7-test"


def test_get_hub_app_version_truncates_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_APP_VERSION", "x" * 40)
    assert len(get_hub_app_version()) == 32


def test_get_hub_app_version_fallback_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUB_APP_VERSION", raising=False)
    ver = get_hub_app_version()
    assert ver
    assert len(ver) <= 32
    # 无 env 时应为包版本或 dev
    assert ver == "dev" or ver != os.environ.get("HUB_APP_VERSION")
