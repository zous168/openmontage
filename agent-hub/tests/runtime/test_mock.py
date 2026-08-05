"""CR-80: unified MXAI_MOCK runtime switch."""

from __future__ import annotations

import pytest

from plugins.mxai.runtime.mock import is_mxai_mock


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
    ],
)
def test_is_mxai_mock(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    if value:
        monkeypatch.setenv("MXAI_MOCK", value)
    else:
        monkeypatch.delenv("MXAI_MOCK", raising=False)
    assert is_mxai_mock() is expected
