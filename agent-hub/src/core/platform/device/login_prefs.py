"""本机 AI 员工登录表单凭证 — ``{HUB_DATA_DIR}/device/login_prefs.json``.

与 ``device_auth.json``（会话票）分文件：此处仅存「记住账号/密码」表单偏好，
供 agent-client 登录页与 Hub ``/login`` 统一读写（本机 loopback）。
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)
_lock = threading.RLock()


@dataclass(frozen=True)
class LoginPrefs:
    login_name: str = ""
    password: str = ""
    remember_password: bool = False
    auto_login: bool = False

    def to_api(self) -> dict[str, object]:
        return {
            "login_name": self.login_name,
            "password": self.password if self.remember_password else "",
            "remember_password": self.remember_password,
            "auto_login": bool(self.auto_login and self.remember_password),
        }


def _prefs_path() -> Path:
    from runtime_paths import resolve_hub_data_dir_path

    return resolve_hub_data_dir_path() / "device" / "login_prefs.json"


def load_login_prefs() -> LoginPrefs:
    with _lock:
        path = _prefs_path()
        if not path.is_file():
            return LoginPrefs()
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("login prefs load failed path=%s error=%s", path, exc)
            return LoginPrefs()
        remember = bool(raw.get("remember_password"))
        login_name = str(raw.get("login_name") or "").strip()
        password = str(raw.get("password") or "") if remember else ""
        auto_login = bool(raw.get("auto_login")) and remember and bool(password)
        return LoginPrefs(
            login_name=login_name,
            password=password,
            remember_password=remember,
            auto_login=auto_login,
        )


def save_login_prefs(
    *,
    login_name: str,
    password: str = "",
    remember_password: bool = False,
    auto_login: bool = False,
) -> LoginPrefs:
    name = (login_name or "").strip()
    remember = bool(remember_password) and bool(name or password)
    pwd = (password or "") if remember else ""
    auto = bool(auto_login) and remember and bool(pwd)
    prefs = LoginPrefs(
        login_name=name,
        password=pwd,
        remember_password=remember,
        auto_login=auto,
    )
    with _lock:
        path = _prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "login_name": prefs.login_name,
                "password": prefs.password,
                "remember_password": prefs.remember_password,
                "auto_login": prefs.auto_login,
            },
            ensure_ascii=False,
            indent=2,
        )
        path.write_text(payload + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return prefs


def clear_login_prefs() -> None:
    with _lock:
        path = _prefs_path()
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            _log.warning("login prefs clear failed path=%s error=%s", path, exc)
