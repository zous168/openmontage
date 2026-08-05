"""素材快照与可达性校验。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from plugins.mxai.content.media_snapshot import (
    VC_R2V_REFS_UNRESOLVED,
    build_ref_catalog,
    build_refs_trace_summary,
    build_r2v_resolved_media,
    freeze_generate_snapshot,
    media_items_from_snapshot,
    r2v_snapshot_valid,
    sha256_hex,
    validate_media_reachable,
)


def test_build_ref_catalog_includes_oss_and_sha256() -> None:
    params = {
        "refs": [
            {
                "id": "p1",
                "url": "https://cdn/p1.jpg",
                "oss_key": "uploads/t/u1.jpg",
                "sha256": "abc123",
            },
        ],
    }
    catalog = build_ref_catalog(params, None)
    assert catalog["p1"]["oss_key"] == "uploads/t/u1.jpg"
    assert catalog["p1"]["sha256"] == "abc123"


def test_build_r2v_resolved_media_from_ref_ids() -> None:
    params = {
        "refs": [
            {
                "id": "p1",
                "url": "https://cdn/p1.jpg",
                "oss_key": "uploads/t/u1.jpg",
                "sha256": "deadbeef",
            },
        ],
    }
    shot = {"ref_ids": ["p1"]}
    resolved = build_r2v_resolved_media(shot, params=params)
    assert len(resolved) == 1
    assert resolved[0]["url"] == "https://cdn/p1.jpg"
    assert resolved[0]["oss_key"] == "uploads/t/u1.jpg"
    assert resolved[0]["sha256"] == "deadbeef"


def test_freeze_generate_snapshot_r2v() -> None:
    params = {"refs": [{"id": "a", "url": "https://x/a.jpg", "oss_key": "k/a"}]}
    shot = {"ref_ids": ["a"], "gen_mode": "r2v"}
    snap = freeze_generate_snapshot(shot, params=params, gen_mode="r2v")
    assert snap["gen_mode"] == "r2v"
    assert len(snap["resolved_media"]) == 1


def test_media_items_from_snapshot() -> None:
    media = media_items_from_snapshot(
        [{"ref_id": "p1", "url": "https://cdn/p1.jpg", "role": "product"}],
    )
    assert media == [{"type": "reference_image", "url": "https://cdn/p1.jpg", "role": "product", "ref_id": "p1"}]


def test_validate_media_reachable_ok() -> None:
    resp = MagicMock(status_code=200)
    with patch("plugins.mxai.content.media_snapshot.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.head.return_value = resp
        ok, reason = validate_media_reachable([{"url": "https://cdn/p1.jpg", "ref_id": "p1"}])
    assert ok is True
    assert reason is None


def test_validate_media_reachable_fail() -> None:
    with patch("plugins.mxai.content.media_snapshot.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.head.side_effect = Exception("network")
        client.get.side_effect = Exception("network")
        ok, reason = validate_media_reachable([{"url": "https://cdn/missing.jpg", "ref_id": "p1"}])
    assert ok is False
    assert reason == "p1"


def test_build_refs_trace_summary() -> None:
    summary = build_refs_trace_summary(
        [
            {
                "ref_id": "p1",
                "url": "https://cdn.example/very/long/path/p1.jpg",
                "oss_key": "uploads/t/p1.jpg",
                "sha256": "abcdef0123456789",
            },
        ],
    )
    assert summary["ref_count"] == 1
    assert summary["ref_ids"] == ["p1"]
    assert summary["refs_digest"][0]["sha256_prefix"] == "abcdef0123456789"


def test_r2v_snapshot_valid() -> None:
    assert r2v_snapshot_valid({"resolved_media": [{"url": "https://x/a.jpg"}]}) is True
    assert r2v_snapshot_valid({"resolved_media": []}) is False


def test_sha256_hex() -> None:
    assert sha256_hex(b"hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
