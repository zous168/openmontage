"""Stable device id for control-server device login."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def get_or_create_device_id() -> str:
    """Return env override or persisted stable id under ``{HUB_DATA_DIR}/device/``."""
    env_id = (os.environ.get("HUB_DEVICE_ID") or "").strip()
    if env_id:
        return env_id
    from runtime_paths import resolve_hub_data_dir_path

    path = resolve_hub_data_dir_path() / "device" / "device_id.txt"
    if path.is_file():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    device_id = f"hub-{secrets.token_hex(8)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(device_id + "\n", encoding="utf-8")
    return device_id
