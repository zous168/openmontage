"""ClawBot SSOT 存储（config + channel_directory）与 legacy 搬迁测试."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from gateway.channel_directory import load_directory
from gateway.platforms.clawbot.config import load_clawbot_config
from gateway.platforms.clawbot.storage import (
    ClawbotContextTokenStore,
    consolidate_clawbot_runtime_ssot,
    migrate_weixin_accounts_to_flat,
)


def _patch_hermes_home(monkeypatch, tmp_path: Path) -> None:
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(cfg_mod, "get_hermes_home", lambda: tmp_path)


def _seed_legacy_accounts(data_dir: Path, account_id: str = "bot@im.bot") -> None:
    root = data_dir / "weixin" / "accounts"
    root.mkdir(parents=True)
    (root / f"{account_id}.json").write_text(
        json.dumps(
            {
                "token": "legacy_tok",
                "base_url": "https://ilinkai.weixin.qq.com",
                "user_id": "wx@im.wechat",
            }
        ),
        encoding="utf-8",
    )
    (root / f"{account_id}.context-tokens.json").write_text(
        json.dumps({"wx@im.wechat": "ctx1", "peer2@im.wechat": "ctx2"}),
        encoding="utf-8",
    )
    (root / f"{account_id}.sync.json").write_text(
        json.dumps({"get_updates_buf": "cursor-abc"}),
        encoding="utf-8",
    )


def test_migrate_weixin_accounts_to_flat_writes_ssot(monkeypatch, tmp_path: Path) -> None:
    _patch_hermes_home(monkeypatch, tmp_path)
    _seed_legacy_accounts(tmp_path)

    moved = migrate_weixin_accounts_to_flat(tmp_path)

    assert moved >= 3
    assert not (tmp_path / "weixin" / "accounts").exists()
    directory = load_directory()
    clawbot = {ch["id"]: ch for ch in directory.get("platforms", {}).get("clawbot", [])}
    assert clawbot["wx@im.wechat"]["context_token"] == "ctx1"
    assert clawbot["peer2@im.wechat"]["context_token"] == "ctx2"
    assert load_clawbot_config()["get_updates_buf"] == "cursor-abc"
    assert migrate_weixin_accounts_to_flat(tmp_path) == 0


def test_consolidate_sidecar_json_to_ssot(monkeypatch, tmp_path: Path) -> None:
    _patch_hermes_home(monkeypatch, tmp_path)
    (tmp_path / "clawbot_context_tokens.json").write_text(
        json.dumps({"user@im.wechat": "tok-sidecar"}),
        encoding="utf-8",
    )
    (tmp_path / "clawbot_sync.json").write_text(
        json.dumps({"get_updates_buf": "buf-sidecar"}),
        encoding="utf-8",
    )

    moved = consolidate_clawbot_runtime_ssot(tmp_path)

    assert moved >= 2
    assert not (tmp_path / "clawbot_context_tokens.json").exists()
    assert not (tmp_path / "clawbot_sync.json").exists()
    directory = load_directory()
    clawbot = directory.get("platforms", {}).get("clawbot", [])
    assert any(ch.get("id") == "user@im.wechat" and ch.get("context_token") == "tok-sidecar" for ch in clawbot)
    assert load_clawbot_config()["get_updates_buf"] == "buf-sidecar"


def test_clawbot_context_token_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    _patch_hermes_home(monkeypatch, tmp_path)

    store = ClawbotContextTokenStore(tmp_path)
    store.set("acc@im.bot", "user@im.wechat", "tok123")
    store2 = ClawbotContextTokenStore(tmp_path)
    store2.restore("acc@im.bot")
    assert store2.get("acc@im.bot", "user@im.wechat") == "tok123"

    directory = load_directory()
    entry = next(ch for ch in directory["platforms"]["clawbot"] if ch["id"] == "user@im.wechat")
    assert entry["context_token"] == "tok123"


def test_channel_directory_rebuild_preserves_context_token(monkeypatch, tmp_path: Path) -> None:
    _patch_hermes_home(monkeypatch, tmp_path)
    directory_path = tmp_path / "channel_directory.json"
    directory_path.write_text(
        json.dumps(
            {
                "updated_at": "old",
                "platforms": {
                    "clawbot": [
                        {
                            "id": "peer@im.wechat",
                            "name": "peer@im.wechat",
                            "type": "dm",
                            "context_token": "keep-me",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    from gateway.channel_directory import _merge_platform_runtime_fields

    merged = _merge_platform_runtime_fields(
        json.loads(directory_path.read_text(encoding="utf-8")),
        {
            "updated_at": "new",
            "platforms": {
                "clawbot": [
                    {
                        "id": "peer@im.wechat",
                        "name": "peer@im.wechat",
                        "type": "dm",
                        "thread_id": None,
                    }
                ]
            },
        },
        "clawbot",
        ("context_token",),
    )
    assert merged["platforms"]["clawbot"][0]["context_token"] == "keep-me"
