"""Backlot application-wide settings (defaults + UI preferences)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from plugins.openmontage.lib.paths import BACKLOT_STATE_DIR, DATA_ROOT, PROJECTS_DIR, REPO_ROOT

from plugins.openmontage.backlot.bootstrap import BootstrapError, list_style_playbook_options

SETTINGS_DIR = BACKLOT_STATE_DIR
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": "1.0",
    "default_style_playbook": "",
    "default_bootstrap_notes": "",
    "theme": "dark",
    "font_scale": 1.12,
}

_FONT_SCALE_MIN = 0.85
_FONT_SCALE_MAX = 1.4


def _settings_path(path: Optional[Path] = None) -> Path:
    return path or SETTINGS_PATH


def load_app_settings(settings_path: Optional[Path] = None) -> dict[str, Any]:
    """Read persisted app settings; missing keys fall back to defaults."""
    path = _settings_path(settings_path)
    data = dict(DEFAULT_SETTINGS)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except (json.JSONDecodeError, OSError):
            pass
    data["default_style_playbook"] = str(data.get("default_style_playbook") or "")
    data["default_bootstrap_notes"] = str(data.get("default_bootstrap_notes") or "")
    theme = str(data.get("theme") or "dark").strip().lower()
    data["theme"] = "light" if theme == "light" else "dark"
    try:
        scale = float(data.get("font_scale", DEFAULT_SETTINGS["font_scale"]))
    except (TypeError, ValueError):
        scale = DEFAULT_SETTINGS["font_scale"]
    data["font_scale"] = max(_FONT_SCALE_MIN, min(_FONT_SCALE_MAX, round(scale, 2)))
    return data


def app_settings_response(settings_path: Optional[Path] = None) -> dict[str, Any]:
    """Payload for GET /api/settings."""
    settings = load_app_settings(settings_path)
    return {
        **settings,
        "style_playbook_options": list_style_playbook_options(),
        "projects_dir": str(PROJECTS_DIR.resolve()),
        "repo_root": str(REPO_ROOT.resolve()),
        # 作为 Hermes 插件运行时数据根会离开仓库，两者不再相同。
        "data_root": str(DATA_ROOT.resolve()),
    }


def update_app_settings(
    *,
    default_style_playbook: Optional[str] = None,
    default_bootstrap_notes: Optional[str] = None,
    theme: Optional[str] = None,
    font_scale: Optional[float] = None,
    settings_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Merge and persist app settings."""
    path = _settings_path(settings_path)
    current = load_app_settings(path)

    if default_style_playbook is not None:
        sp = default_style_playbook.strip()
        if sp:
            allowed = {o["value"] for o in list_style_playbook_options() if o["value"]}
            if sp not in allowed:
                raise BootstrapError("无效的视觉风格。")
            current["default_style_playbook"] = sp
        else:
            current["default_style_playbook"] = ""

    if default_bootstrap_notes is not None:
        current["default_bootstrap_notes"] = default_bootstrap_notes.strip()[:2000]

    if theme is not None:
        th = theme.strip().lower()
        if th not in ("dark", "light"):
            raise BootstrapError("主题须为 dark 或 light。")
        current["theme"] = th

    if font_scale is not None:
        try:
            scale = float(font_scale)
        except (TypeError, ValueError):
            raise BootstrapError("界面字号须为数字。") from None
        if scale < _FONT_SCALE_MIN or scale > _FONT_SCALE_MAX:
            raise BootstrapError(f"界面字号须在 {_FONT_SCALE_MIN}–{_FONT_SCALE_MAX} 之间。")
        current["font_scale"] = round(scale, 2)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return app_settings_response(path)
