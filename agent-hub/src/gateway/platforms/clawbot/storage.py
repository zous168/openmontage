"""ClawBot 运行时存储 SSOT（CR-145 · 替代 ``weixin/accounts/`` 与散落 JSON）。

单账号 ClawBot/iLink；**凭据 + poll 游标** → ``config.yaml`` → ``platforms.clawbot``；
**per-peer context_token** → ``channel_directory.json`` → ``platforms.clawbot[]`` 条目字段。

与 Gateway 其它平台惯例一致（``channel_directory`` / ``config.yaml`` 为根级 SSOT）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from gateway.channel_directory import (
    get_platform_channel_field,
    patch_platform_channel_fields,
)
from gateway.platforms.clawbot.config import (
    load_clawbot_sync_buf as _load_sync_from_config,
    patch_clawbot_config,
    save_clawbot_sync_buf as _save_sync_to_config,
)

logger = logging.getLogger(__name__)

_CLAWBOT_PLATFORM = "clawbot"
_LEGACY_ACCOUNTS_DIR = Path("weixin") / "accounts"
# m0004 过渡期：曾短暂落数据根的 sidecar（m0005 迁入 config/directory 后删除）
_LEGACY_CONTEXT_TOKENS_FILE = "clawbot_context_tokens.json"
_LEGACY_SYNC_FILE = "clawbot_sync.json"


class ClawbotContextTokenStore:
    """per-peer ``context_token``；磁盘格式为 channel_directory 条目上的 ``context_token`` 字段。"""

    def __init__(self, hermes_home: str | Path):
        self._home = Path(hermes_home)
        self._cache: dict[str, str] = {}

    def _key(self, account_id: str, user_id: str) -> str:
        del account_id
        return str(user_id or "").strip()

    def restore(self, account_id: str) -> None:
        del account_id
        from gateway.channel_directory import load_directory

        directory = load_directory()
        restored = 0
        for ch in directory.get("platforms", {}).get(_CLAWBOT_PLATFORM, []):
            peer_id = str(ch.get("id") or "").strip()
            token = str(ch.get("context_token") or "").strip()
            if peer_id and token:
                self._cache[peer_id] = token
                restored += 1
        if restored:
            logger.info("clawbot: restored %d context token(s) from channel_directory", restored)
            return

        # 读回落：m0004 短暂 sidecar 或 legacy weixin/accounts
        legacy_sidecar = self._home / _LEGACY_CONTEXT_TOKENS_FILE
        if legacy_sidecar.is_file():
            self._load_legacy_token_map(legacy_sidecar)
            if self._cache:
                logger.info("clawbot: restored %d context token(s) from legacy sidecar", len(self._cache))
                for peer_id, token in self._cache.items():
                    patch_platform_channel_fields(_CLAWBOT_PLATFORM, peer_id, context_token=token)
            return

        legacy_root = self._home / _LEGACY_ACCOUNTS_DIR
        if not legacy_root.is_dir():
            return
        merged = 0
        for legacy in sorted(legacy_root.glob("*.context-tokens.json")):
            before = len(self._cache)
            self._load_legacy_token_map(legacy)
            merged += len(self._cache) - before
        if merged:
            logger.info("clawbot: restored %d context token(s) from legacy weixin/accounts", merged)
            for peer_id, token in self._cache.items():
                patch_platform_channel_fields(_CLAWBOT_PLATFORM, peer_id, context_token=token)

    def get(self, account_id: str, user_id: str) -> Optional[str]:
        key = self._key(account_id, user_id)
        cached = self._cache.get(key)
        if cached:
            return cached
        token = get_platform_channel_field(_CLAWBOT_PLATFORM, key, "context_token")
        if token:
            self._cache[key] = token
        return token

    def set(self, account_id: str, user_id: str, token: str) -> None:
        key = self._key(account_id, user_id)
        if not key or not str(token or "").strip():
            return
        self._cache[key] = token
        patch_platform_channel_fields(_CLAWBOT_PLATFORM, key, context_token=token)

    def _load_legacy_token_map(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("clawbot: failed to read context tokens %s: %s", path, exc)
            return
        if not isinstance(data, dict):
            return
        for user_id, tok in data.items():
            if isinstance(user_id, str) and isinstance(tok, str) and tok.strip():
                self._cache[user_id.strip()] = tok


def _legacy_accounts_dir(data_dir: Path) -> Path:
    return data_dir / _LEGACY_ACCOUNTS_DIR


def _resolve_active_account_id(data_dir: Path) -> str:
    try:
        from gateway.platforms.clawbot.config import load_clawbot_config

        aid = str(load_clawbot_config().get("account_id") or "").strip()
        if aid:
            return aid
    except Exception:
        pass
    legacy = _legacy_accounts_dir(data_dir)
    if not legacy.is_dir():
        return ""
    candidates = sorted(
        (p for p in legacy.glob("*.json") if ".context-tokens" not in p.name and ".sync" not in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0].stem
    return ""


def _patch_clawbot_from_legacy_account(data_dir: Path, account_id: str) -> bool:
    legacy_file = _legacy_accounts_dir(data_dir) / f"{account_id}.json"
    if not legacy_file.is_file():
        return False
    try:
        payload = json.loads(legacy_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    token = str(payload.get("token") or "").strip()
    if not token:
        return False
    from gateway.platforms.clawbot.config import load_clawbot_config

    current = load_clawbot_config()
    if current.get("token") and current.get("account_id"):
        return False
    patch_clawbot_config(
        {
            "enabled": True,
            "bind_status": bool(current.get("bind_status")),
            "account_id": account_id,
            "token": token,
            "base_url": str(payload.get("base_url") or "").strip(),
            "user_id": str(payload.get("user_id") or "").strip(),
        }
    )
    logger.info("clawbot-migrate: backfilled platforms.clawbot from legacy %s", legacy_file.name)
    return True


def _import_legacy_sidecar_tokens(data_dir: Path) -> int:
    path = data_dir / _LEGACY_CONTEXT_TOKENS_FILE
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    count = 0
    for uid, tok in data.items():
        if isinstance(uid, str) and isinstance(tok, str) and tok.strip():
            patch_platform_channel_fields(_CLAWBOT_PLATFORM, uid.strip(), context_token=tok)
            count += 1
    return count


def _import_legacy_sidecar_sync(data_dir: Path) -> int:
    path = data_dir / _LEGACY_SYNC_FILE
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    sync_buf = str(payload.get("get_updates_buf") or "").strip()
    if not sync_buf:
        return 0
    from gateway.platforms.clawbot.config import load_clawbot_config

    if not load_clawbot_config().get("get_updates_buf"):
        patch_clawbot_config({"get_updates_buf": sync_buf})
    return 1


def migrate_weixin_accounts_to_flat(data_dir: Path) -> int:
    """一次性搬迁：``weixin/accounts/`` → config/directory SSOT，并删除 legacy 树。

    幂等；返回处理项计数（用于迁移账本）。
    """
    data_dir = Path(data_dir)
    legacy_root = _legacy_accounts_dir(data_dir)
    moved = 0

    account_id = _resolve_active_account_id(data_dir)
    if account_id:
        if _patch_clawbot_from_legacy_account(data_dir, account_id):
            moved += 1

    if legacy_root.is_dir():
        merged_tokens: dict[str, str] = {}
        for legacy in legacy_root.glob("*.context-tokens.json"):
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                for uid, tok in data.items():
                    if isinstance(uid, str) and isinstance(tok, str) and tok.strip():
                        merged_tokens[uid.strip()] = tok
        for uid, tok in merged_tokens.items():
            patch_platform_channel_fields(_CLAWBOT_PLATFORM, uid, context_token=tok)
        if merged_tokens:
            moved += 1
            logger.info("clawbot-migrate: merged %d context token(s) into channel_directory", len(merged_tokens))

        legacy_sync: Path | None = None
        if account_id:
            candidate = legacy_root / f"{account_id}.sync.json"
            if candidate.is_file():
                legacy_sync = candidate
        if legacy_sync is None:
            sync_files = sorted(
                legacy_root.glob("*.sync.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if sync_files:
                legacy_sync = sync_files[0]
        if legacy_sync and legacy_sync.is_file():
            try:
                payload = json.loads(legacy_sync.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            sync_buf = str((payload or {}).get("get_updates_buf") or "").strip() if isinstance(payload, dict) else ""
            if sync_buf:
                from gateway.platforms.clawbot.config import load_clawbot_config

                if not load_clawbot_config().get("get_updates_buf"):
                    patch_clawbot_config({"get_updates_buf": sync_buf})
                moved += 1
                logger.info("clawbot-migrate: copied sync cursor into config.yaml")

        legacy_files = list(legacy_root.iterdir())
        if legacy_files:
            for f in legacy_files:
                try:
                    f.unlink()
                except OSError:
                    logger.warning("clawbot-migrate: failed to delete %s", f, exc_info=True)
            moved += len(legacy_files)
        try:
            legacy_root.rmdir()
        except OSError:
            pass
        weixin_root = data_dir / "weixin"
        if weixin_root.is_dir() and not any(weixin_root.iterdir()):
            try:
                weixin_root.rmdir()
            except OSError:
                pass
        if legacy_files:
            logger.info("clawbot-migrate: removed legacy %s (%d files)", legacy_root, len(legacy_files))

    moved += consolidate_clawbot_runtime_ssot(data_dir)

    return moved


def consolidate_clawbot_runtime_ssot(data_dir: Path) -> int:
    """m0004 之后：sidecar JSON → config/directory，删 ``clawbot_*.json``。幂等。"""
    data_dir = Path(data_dir)
    moved = _import_legacy_sidecar_tokens(data_dir)
    moved += _import_legacy_sidecar_sync(data_dir)
    for legacy_name in (_LEGACY_CONTEXT_TOKENS_FILE, _LEGACY_SYNC_FILE):
        legacy_path = data_dir / legacy_name
        if legacy_path.is_file():
            try:
                legacy_path.unlink()
                moved += 1
            except OSError:
                logger.warning("clawbot-migrate: failed to delete %s", legacy_path, exc_info=True)
    return moved


def load_clawbot_sync_buf(hermes_home: str | Path) -> str:
    """``WeixinAdapter`` 调用面；账号级游标读 ``config.yaml``。"""
    del hermes_home
    return _load_sync_from_config()


def save_clawbot_sync_buf(hermes_home: str | Path, sync_buf: str) -> None:
    """``WeixinAdapter`` 调用面；账号级游标写 ``config.yaml``。"""
    del hermes_home
    _save_sync_to_config(sync_buf)
