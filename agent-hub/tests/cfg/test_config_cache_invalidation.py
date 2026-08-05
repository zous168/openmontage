"""Profile config cache must refresh when global model changes."""

from __future__ import annotations

import yaml

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from hermes_cli.config import (
    _LOAD_CONFIG_CACHE,
    invalidate_config_caches,
    load_config,
    save_config,
)


def test_global_model_change_invalidates_profile_cache(tmp_path, monkeypatch) -> None:
    root = tmp_path / "hub"
    root.mkdir()
    profile_dir = root / "profiles" / "douyin"
    profile_dir.mkdir(parents=True)

    (root / "config.yaml").write_text(
        yaml.safe_dump({"model": {"provider": "moark", "default": "Old-Model"}}),
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump({"agent": {"max_turns": 90}}),
        encoding="utf-8",
    )

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    monkeypatch.delenv("HERMES_PROFILE", raising=False)

    invalidate_config_caches(global_change=True)

    token = set_hermes_home_override(str(profile_dir))
    try:
        cfg1 = load_config()
        assert cfg1["model"]["default"] == "Old-Model"
        profile_path_key = str(profile_dir / "config.yaml")
        assert profile_path_key in _LOAD_CONFIG_CACHE
    finally:
        reset_hermes_home_override(token)

    token_root = set_hermes_home_override(str(root))
    try:
        global_cfg = load_config()
        global_cfg["model"] = {"provider": "moark", "default": "New-Model"}
        save_config(global_cfg)
    finally:
        reset_hermes_home_override(token_root)

    token = set_hermes_home_override(str(profile_dir))
    try:
        cfg2 = load_config()
        assert cfg2["model"]["default"] == "New-Model"
    finally:
        reset_hermes_home_override(token)


def test_profile_patch_only_invalidates_own_path(tmp_path, monkeypatch) -> None:
    root = tmp_path / "hub"
    root.mkdir()
    profile_dir = root / "profiles" / "douyin"
    profile_dir.mkdir(parents=True)

    (root / "config.yaml").write_text(
        yaml.safe_dump({"model": {"provider": "moark", "default": "Global-Model"}}),
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump({"model": {"provider": "moark", "default": "Profile-Old"}}),
        encoding="utf-8",
    )

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))

    invalidate_config_caches(global_change=True)

    other_dir = root / "profiles" / "wechat"
    other_dir.mkdir(parents=True)
    (other_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")

    token_other = set_hermes_home_override(str(other_dir))
    try:
        load_config()
        other_key = str(other_dir / "config.yaml")
        assert other_key in _LOAD_CONFIG_CACHE
    finally:
        reset_hermes_home_override(token_other)

    token = set_hermes_home_override(str(profile_dir))
    try:
        cfg = load_config()
        cfg["model"] = {"provider": "moark", "default": "Profile-New"}
        save_config(cfg)
        profile_key = str(profile_dir / "config.yaml")
        assert profile_key not in _LOAD_CONFIG_CACHE or load_config()["model"]["default"] == "Profile-New"
    finally:
        reset_hermes_home_override(token)

    token_other = set_hermes_home_override(str(other_dir))
    try:
        assert str(other_dir / "config.yaml") in _LOAD_CONFIG_CACHE
    finally:
        reset_hermes_home_override(token_other)
