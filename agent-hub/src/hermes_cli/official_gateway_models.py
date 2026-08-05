"""官方渠道（系统内置模型）—— 供模型选择器 / 默认主模型使用。

运行时路由见 ``runtime_provider._resolve_official_runtime``；本模块只负责：
- 判定官方渠道是否可用（网关 URL + 设备 JWT）
- 从 ``{LLM_GATEWAY_BASE_URL}/v1/models`` 拉模型列表（带进程/磁盘缓存）
- 登录后把未配置的主模型落到 ``official``
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

from core.platform.gateway_base_url import resolve_llm_gateway_base_url

OFFICIAL_PROVIDER_SLUG = "official"
OFFICIAL_PROVIDER_LABEL = "系统内置模型"

# 与 hermes_cli.models._PROVIDER_MODELS_CACHE_TTL 对齐
_OFFICIAL_MODELS_CACHE_TTL = 3600
# 进程内缓存：同一次 /api/model/options 内多次调用只打一次网关
_mem_cache: dict | None = None  # {"fp": str, "at": float, "models": list[str]}


def official_gateway_base_url() -> str:
    return resolve_llm_gateway_base_url()


def current_device_jwt() -> str:
    try:
        from core.platform.device.device_auth_service import get_fresh_device_access_token

        return get_fresh_device_access_token()
    except Exception:
        return ""


def is_official_channel_ready() -> bool:
    return bool(official_gateway_base_url() and current_device_jwt())


def _cache_fingerprint() -> str:
    """网关地址 + 设备登录态变化时使缓存失效。"""
    parts = [f"base={official_gateway_base_url()}"]
    try:
        from core.platform.device.local_device_auth import LocalDeviceAuthStore
        from runtime_paths import resolve_hub_data_dir_path

        path = resolve_hub_data_dir_path() / "device" / "device_auth.json"
        try:
            parts.append(f"auth@{path.stat().st_mtime_ns}")
        except FileNotFoundError:
            parts.append("auth@missing")
        auth = LocalDeviceAuthStore().load()
        if auth is not None:
            parts.append(f"user={auth.user_id}")
            parts.append(f"tenant={auth.tenant_id}")
    except Exception:
        parts.append("auth@unknown")
    blob = "|".join(parts).encode("utf-8", errors="replace")
    return hashlib.blake2b(blob, digest_size=8).hexdigest()


def _disk_cache_path():
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "official_gateway_models_cache.json"


def _read_disk_cache() -> dict:
    try:
        path = _disk_cache_path()
        if not path.is_file():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_disk_cache(data: dict) -> None:
    try:
        path = _disk_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.debug("official models disk cache write failed: %s", exc)


def clear_official_gateway_models_cache() -> None:
    """登出或网关切换后可主动清缓存。"""
    global _mem_cache
    _mem_cache = None
    try:
        path = _disk_cache_path()
        if path.is_file():
            path.unlink()
    except Exception:
        pass


def fetch_official_gateway_models(
    *,
    timeout: float = 3.0,
    force_refresh: bool = False,
) -> list[str]:
    """``GET {gateway}/v1/models``，Bearer = 设备 JWT。

    命中进程/磁盘缓存（TTL 1h）时不打网关；失败返回空列表（磁盘有同指纹
    过期条目时回退到过期数据，避免闪断导致 picker 空白）。
    """
    global _mem_cache

    base = official_gateway_base_url()
    jwt = current_device_jwt()
    if not base or not jwt:
        return []

    fp = _cache_fingerprint()
    now = time.time()

    if not force_refresh and isinstance(_mem_cache, dict):
        if (
            _mem_cache.get("fp") == fp
            and isinstance(_mem_cache.get("models"), list)
            and _mem_cache["models"]
            and (now - float(_mem_cache.get("at", 0))) < _OFFICIAL_MODELS_CACHE_TTL
        ):
            return list(_mem_cache["models"])

    disk = _read_disk_cache()
    if (
        not force_refresh
        and disk.get("fp") == fp
        and isinstance(disk.get("models"), list)
        and disk["models"]
        and (now - float(disk.get("at", 0))) < _OFFICIAL_MODELS_CACHE_TTL
    ):
        models = [str(m).strip() for m in disk["models"] if str(m).strip()]
        _mem_cache = {"fp": fp, "at": float(disk.get("at", now)), "models": models}
        return list(models)

    try:
        from hermes_cli.models import fetch_api_models

        live = fetch_api_models(jwt, base, timeout=timeout) or []
        models = [str(m).strip() for m in live if str(m).strip()]
    except Exception as e:
        logger.debug("official gateway /v1/models failed: %s", e)
        models = []

    if models:
        entry = {"fp": fp, "at": now, "models": models}
        _mem_cache = entry
        _write_disk_cache(entry)
        return list(models)

    # live 失败：同指纹的过期磁盘数据优于空列表
    if (
        disk.get("fp") == fp
        and isinstance(disk.get("models"), list)
        and disk["models"]
    ):
        stale = [str(m).strip() for m in disk["models"] if str(m).strip()]
        _mem_cache = {"fp": fp, "at": float(disk.get("at", 0)), "models": stale}
        return list(stale)

    return []


def get_official_default_model(models: Optional[list[str]] = None) -> str:
    ids = list(models) if models is not None else fetch_official_gateway_models()
    return ids[0] if ids else ""


def ensure_official_as_default_main_model(*, force: bool = False) -> bool:
    """官方渠道就绪时，将主模型设为系统内置（写入当前 profile config.yaml）。

    - ``force=False``（默认）：仅当当前 ``provider`` 为空 / ``auto``，或 ``model`` 为空时写入。
    - ``force=True``：登录成功后强制切到内置（产品默认）。
    返回是否写入了配置。
    """
    if not is_official_channel_ready():
        return False

    try:
        from hermes_cli.config import load_config, save_config
        from hermes_cli.web_routes.config import apply_main_model_assignment
    except Exception as e:
        logger.warning("official default: config helpers unavailable: %s", e)
        return False

    cfg = load_config() or {}
    model_cfg = cfg.get("model")
    if isinstance(model_cfg, str):
        model_cfg = {"default": model_cfg, "provider": ""}
    if not isinstance(model_cfg, dict):
        model_cfg = {}

    cur_provider = str(model_cfg.get("provider") or "").strip().lower()
    cur_model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
    # 已配置则直接返回，避免每次打开设置页都打网关
    if not force:
        if cur_provider and cur_provider not in {"auto", "official"} and cur_model:
            return False
        if cur_provider == "official" and cur_model:
            return False

    models = fetch_official_gateway_models()
    default_model = get_official_default_model(models)
    if not default_model:
        logger.info("official channel ready but gateway returned no models; skip default")
        return False

    apply_main_model_assignment(model_cfg, OFFICIAL_PROVIDER_SLUG, default_model)
    # 官方渠道 base_url/api_key 由 runtime 实时注入，勿固化到 config
    model_cfg["base_url"] = ""
    model_cfg["api_key"] = ""
    cfg["model"] = model_cfg
    save_config(cfg)
    logger.info(
        "official default main model set provider=%s model=%s force=%s",
        OFFICIAL_PROVIDER_SLUG,
        default_model,
        force,
    )
    return True
