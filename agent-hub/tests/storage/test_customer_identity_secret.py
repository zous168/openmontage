"""customer_identity HMAC 密钥读取容错."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.storage.customer_identity import _read_secret_bytes, _SECRET_BYTES


def test_read_secret_bytes_accepts_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "key"
    secret = b"a" * _SECRET_BYTES
    path.write_bytes(secret + b"\n")
    assert _read_secret_bytes(path) == secret


def test_read_secret_bytes_truncates_extra_byte(tmp_path: Path) -> None:
    path = tmp_path / "key"
    secret = b"b" * _SECRET_BYTES
    path.write_bytes(secret + b"{")
    assert _read_secret_bytes(path) == secret


def test_read_secret_bytes_rejects_too_short(tmp_path: Path) -> None:
    path = tmp_path / "key"
    path.write_bytes(b"short")
    with pytest.raises(RuntimeError, match="invalid"):
        _read_secret_bytes(path)
