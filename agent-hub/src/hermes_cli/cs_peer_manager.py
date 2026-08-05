"""客服会话记录 CRUD（dashboard 侧；Agent 运行在网关 ``api_server``）。

收敛架构（docs §七）：建会话 / 删会话经 ``POST|DELETE /api/sessions``（``source=api_server``）；
读写 transcript 与 ``profiles/{profile}/state.db`` 对齐（与 ``X-Hermes-Profile`` 同库）。
聊天由 ``sim_api`` 代理到 ``/api/sessions/{id}/chat``。

会话主体 = (``channel``, ``user_unique_id``)；``session_id`` =
``mxai-{profile}-inbound-{hash(channel:uid)[:16]}``（与 MxAI inbound 命名族一致）。
人设 / 凭证 / toolset 仅来自 profile 目录（``SOUL.md``、``config.yaml`` 等），本模块不写业务文案。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CUSTOMER_PROFILE = "customer"


def cs_sim_session_id(profile: str, channel: str, user_unique_id: str) -> str:
    """客户模拟 session id（与 ``hermes.inbound_session_id`` 同构，hash 含 channel）."""
    slug = hashlib.sha256(f"{channel}:{user_unique_id}".encode()).hexdigest()[:16]
    return f"mxai-{profile}-inbound-{slug}"


def _api_server_base() -> str:
    host = (os.getenv("API_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.getenv("API_SERVER_PORT") or "8642").strip() or "8642"
    return f"http://{host}:{port}"


def _api_server_key() -> str:
    return (os.getenv("API_SERVER_KEY") or "").strip()


def _profile_db(profile: str):
    from hermes_state import SessionDB
    from hermes_cli.profiles import get_profile_dir

    return SessionDB(db_path=get_profile_dir(profile) / "state.db")


def ensure_profile(name: str = _CUSTOMER_PROFILE) -> Path:
    """确保业务 profile 目录存在；人设仅从模板 / Dashboard 配置补缺，不在代码里写 SOUL."""
    import shutil

    import yaml

    from hermes_cli.profiles import get_profile_dir
    from hermes_constants import get_default_hermes_root

    pdir = get_profile_dir(name)
    pdir.mkdir(parents=True, exist_ok=True)
    default_root = get_default_hermes_root()
    for sub in ("memories", "skills", "workspace"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)
    for fn in ("config.yaml", ".env", "auth.json"):
        src = default_root / fn
        if src.exists() and not (pdir / fn).exists():
            try:
                shutil.copy2(src, pdir / fn)
            except OSError:
                logger.debug("复制 %s 到 %s 失败", fn, name, exc_info=True)

    cfgp = pdir / "config.yaml"
    try:
        data = yaml.safe_load(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
        data = data if isinstance(data, dict) else {}
        data.setdefault("curator", {})["enabled"] = False
        data.setdefault("memory", {})["nudge_interval"] = 0
        data.setdefault("agent", {})["skill_nudge_interval"] = 0
        cfgp.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    except Exception:
        logger.warning("patch %s config 失败", name, exc_info=True)

    _seed_profile_prompts(pdir, name)

    return pdir


def _seed_profile_prompts(pdir: Path, name: str) -> None:
    """由业务插件补齐人设与 API toolset —— 缺插件时静默跳过。

    这些 seeder 原先由 ``plugins.mxai`` 提供，该插件已从本仓库移除
    （见 ``agent-hub/UPSTREAM.md``）。它们只负责"补缺"，不提供就保持空白：
    profile 目录本身已经建好，人设由模板或 Dashboard 配置填充。
    """
    try:
        from plugins.mxai.cfg.bootstrap.assistant_profile import (  # type: ignore[import-not-found]
            apply_business_agent_api_toolsets,
        )
        from plugins.mxai.cfg.prompt_config import (  # type: ignore[import-not-found]
            seed_profile_description,
            seed_prompt_files,
        )
    except ImportError:
        logger.debug("业务 profile seeder 不可用，跳过 %s 的人设补缺", name)
        return

    seed_prompt_files(pdir, name)
    seed_profile_description(pdir, name)
    try:
        apply_business_agent_api_toolsets(pdir, name)
    except Exception:
        logger.debug("apply_business_agent_api_toolsets 失败", exc_info=True)


def _post_api_session(
    profile: str,
    session_id: str,
    *,
    user_id: str,
    title: str,
) -> None:
    """``POST /api/sessions`` — 幂等（201 / 409 均视为成功）."""
    key = _api_server_key()
    if not key:
        raise RuntimeError(
            "网关 api_server 未配置 API_SERVER_KEY；请先启用 api_server 平台并配置密钥"
        )
    import httpx

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Hermes-Profile": profile,
    }
    payload = {"id": session_id, "user_id": user_id, "title": title}
    url = f"{_api_server_base()}/api/sessions"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
    if resp.status_code in {200, 201, 409}:
        return
    raise RuntimeError(
        f"POST /api/sessions 失败: {resp.status_code} {resp.text[:300]}"
    )


def _delete_api_session(profile: str, session_id: str) -> bool:
    key = _api_server_key()
    if not key:
        return False
    import httpx

    headers = {
        "Authorization": f"Bearer {key}",
        "X-Hermes-Profile": profile,
    }
    url = f"{_api_server_base()}/api/sessions/{session_id}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.delete(url, headers=headers)
        return resp.status_code in {200, 404}
    except Exception:
        logger.debug("DELETE /api/sessions 失败", exc_info=True)
        return False


class CsPeerManager:
    """客服模拟会话 CRUD（``profiles/{profile}/state.db`` + api_server 建删会话）."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db = None
        self._profile = _CUSTOMER_PROFILE

    def _ensure_ready(self) -> None:
        if self._db is None:
            try:
                ensure_profile(_CUSTOMER_PROFILE)
            except Exception:
                logger.debug("ensure_profile 失败", exc_info=True)
            self._db = _profile_db(_CUSTOMER_PROFILE)

    def _peer_meta(self, channel: str, uid: str, profile: str) -> Dict[str, Any]:
        return {
            "channel": channel,
            "user_unique_id": uid,
            "profile": profile,
            "cs_sim": True,
        }

    def _attach_peer_meta(
        self, session_id: str, channel: str, uid: str, profile: str
    ) -> None:
        meta = self._peer_meta(channel, uid, profile)
        try:
            self._db.update_session_meta(session_id, json.dumps(meta, ensure_ascii=False))
        except Exception:
            logger.debug("update_session_meta 失败", exc_info=True)

    def _ensure_peer_session(
        self,
        channel: str,
        uid: str,
        profile: str,
        *,
        display_name: str,
    ) -> str:
        sid = cs_sim_session_id(profile, channel, uid)
        _post_api_session(profile, sid, user_id=uid, title=display_name)
        self._attach_peer_meta(sid, channel, uid, profile)
        if display_name:
            try:
                self._db.set_session_title(sid, display_name)
            except Exception:
                logger.debug("set_session_title 失败", exc_info=True)
        return sid

    # ---- 主体 CRUD ----
    def create_peer(
        self,
        channel: str,
        user_unique_id: Optional[str] = None,
        user_display_name: Optional[str] = None,
        profile: str = _CUSTOMER_PROFILE,
    ) -> Dict[str, Any]:
        self._ensure_ready()
        ch = (channel or "web").strip() or "web"
        uid = (user_unique_id or "").strip() or f"peer_{uuid.uuid4().hex[:10]}"
        prof = (profile or _CUSTOMER_PROFILE).strip() or _CUSTOMER_PROFILE
        title = (user_display_name or "").strip() or uid
        sid = self._ensure_peer_session(ch, uid, prof, display_name=title)
        row = self._db.get_session(sid) or {}
        return {
            "channel": ch,
            "user_unique_id": uid,
            "user_display_name": row.get("title") or uid,
            "session_id": sid,
            "created_at": row.get("started_at"),
        }

    def list_peers(self) -> List[Dict[str, Any]]:
        self._ensure_ready()
        out: List[Dict[str, Any]] = []
        try:
            rows = self._db.list_sessions_rich(
                limit=1000, order_by_last_active=True
            )
        except Exception:
            return out
        for r in rows:
            if not self._row_is_peer(r):
                continue
            ch, uid = self._meta_of_row(r)
            out.append(
                {
                    "channel": ch,
                    "user_unique_id": uid,
                    "user_display_name": r.get("title") or uid,
                    "created_at": r.get("started_at"),
                    "last_active_at": r.get("last_active") or r.get("started_at"),
                    "rounds": int(r.get("message_count") or 0),
                }
            )
        return out

    def get_history(self, channel: str, user_unique_id: str) -> List[Dict[str, str]]:
        self._ensure_ready()
        sid = self._resolve_session_id(channel, user_unique_id)
        if sid is None:
            return []
        msgs = self._db.get_messages_as_conversation(sid)
        return [
            {"role": m.get("role", ""), "content": m.get("content") or ""}
            for m in msgs
            if m.get("role") in ("user", "assistant") and (m.get("content") or "")
        ]

    def delete_peer(self, channel: str, user_unique_id: str) -> bool:
        self._ensure_ready()
        sid = self._resolve_session_id(channel, user_unique_id)
        if sid is None:
            return False
        meta = self._meta_dict(sid)
        profile = (meta.get("profile") or _CUSTOMER_PROFILE).strip() or _CUSTOMER_PROFILE
        if _delete_api_session(profile, sid):
            return True
        try:
            return bool(self._db.delete_session(sid))
        except Exception:
            logger.debug("delete_session 失败", exc_info=True)
            return False

    def resolve_target(
        self, channel: str, user_unique_id: str
    ) -> Tuple[str, str, str]:
        """返回 ``(session_id, profile, session_key)``；会话不存在则经 api_server 创建."""
        self._ensure_ready()
        ch = (channel or "web").strip() or "web"
        uid = (user_unique_id or "").strip()
        if not uid:
            raise ValueError("user_unique_id 不能为空")
        sid = self._resolve_session_id(ch, uid)
        profile = _CUSTOMER_PROFILE
        if sid is None:
            peer = self.create_peer(ch, user_unique_id=uid, profile=profile)
            sid = peer["session_id"]
        else:
            meta = self._meta_dict(sid)
            profile = (meta.get("profile") or _CUSTOMER_PROFILE).strip() or _CUSTOMER_PROFILE
        session_key = f"agent:{profile}:{ch}:single:{uid}"
        return sid, profile, session_key

    # ---- 内部 ----
    def _resolve_session_id(self, channel: str, uid: str) -> Optional[str]:
        prof = _CUSTOMER_PROFILE
        sid = cs_sim_session_id(prof, channel, uid)
        try:
            if self._db.get_session(sid):
                return sid
        except Exception:
            pass
        try:
            rows = self._db.list_sessions_rich(limit=1000)
        except Exception:
            return None
        for r in rows:
            ch, u = self._meta_of_row(r)
            if u == uid and ch == channel:
                return str(r.get("id"))
        return None

    @staticmethod
    def _row_is_peer(row: Dict[str, Any]) -> bool:
        mc = row.get("model_config")
        if mc:
            try:
                meta = json.loads(mc) if isinstance(mc, str) else mc
                if isinstance(meta, dict) and meta.get("cs_sim"):
                    return True
                if isinstance(meta, dict) and meta.get("user_unique_id"):
                    return True
            except Exception:
                pass
        sid = str(row.get("id") or "")
        return "-inbound-" in sid and bool(row.get("user_id"))

    def _meta_dict(self, sid: str) -> Dict[str, Any]:
        row = self._db.get_session(sid) or {}
        mc = row.get("model_config")
        if mc:
            try:
                meta = json.loads(mc) if isinstance(mc, str) else mc
                if isinstance(meta, dict):
                    return dict(meta)
            except Exception:
                pass
        return {}

    @staticmethod
    def _meta_of_row(row: Dict[str, Any]) -> Tuple[str, str]:
        """从 session 行解析 (channel, user_unique_id)（存在 model_config）."""
        ch, uid = "web", str(row.get("user_id") or row.get("id") or "")
        mc = row.get("model_config")
        if mc:
            try:
                meta = json.loads(mc) if isinstance(mc, str) else mc
                if isinstance(meta, dict):
                    uid = str(meta.get("user_unique_id") or uid)
                    ch = str(meta.get("channel") or "web")
            except Exception:
                pass
        return ch, uid


_MANAGER: Optional[CsPeerManager] = None
_MANAGER_LOCK = threading.Lock()


def get_cs_peer_manager() -> CsPeerManager:
    """进程内单例。"""
    global _MANAGER
    if _MANAGER is None:
        with _MANAGER_LOCK:
            if _MANAGER is None:
                _MANAGER = CsPeerManager()
    return _MANAGER
