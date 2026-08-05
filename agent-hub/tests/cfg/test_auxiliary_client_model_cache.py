"""auxiliary_client auto-provider cache must track persisted main model."""

from __future__ import annotations

import yaml

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from hermes_cli.config import invalidate_config_caches, load_config, save_config


def test_auto_client_cache_key_tracks_persisted_model(tmp_path, monkeypatch) -> None:
    root = tmp_path / "hub"
    root.mkdir()

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))

    (root / "config.yaml").write_text(
        yaml.safe_dump({"model": {"provider": "moark", "default": "Model-A"}}),
        encoding="utf-8",
    )
    invalidate_config_caches(global_change=True)

    from agent.auxiliary_client import _client_cache_key

    token = set_hermes_home_override(str(root))
    try:
        key_a = _client_cache_key("auto", async_mode=False)
        cfg = load_config()
        cfg["model"] = {"provider": "moark", "default": "Model-B"}
        save_config(cfg)
        key_b = _client_cache_key("auto", async_mode=False)
    finally:
        reset_hermes_home_override(token)

    assert key_a != key_b
