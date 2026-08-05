"""本机 IPC token — 存于 ``{HUB_DATA_DIR}/device/local_ipc.token``."""

from __future__ import annotations

import secrets
from pathlib import Path


def _ipc_token_path() -> Path:
    from runtime_paths import resolve_hub_data_dir_path

    return resolve_hub_data_dir_path() / "device" / "local_ipc.token"


def get_or_create_ipc_token() -> str:
    """读取或生成进程间共享的本地 IPC token."""
    path = _ipc_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="utf-8")
    return token


def validate_ipc_token(token: str | None) -> bool:
    """校验调用方携带的 IPC token."""
    if not token or not str(token).strip():
        return False
    expected = get_or_create_ipc_token()
    return secrets.compare_digest(str(token).strip(), expected)
