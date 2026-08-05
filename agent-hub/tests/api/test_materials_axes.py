"""FR-MAT-10：素材形态/访问筛选（不上云集成）。"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def test_materials_upload_kind_access_filter_and_patch(mxai_client: TestClient) -> None:
    lib = mxai_client.post(
        "/api/plugins/mxai/materials/libraries",
        json={"name": "两轴素材库"},
    )
    assert lib.status_code == 200
    library_id = lib.json()["item"]["library_id"]

    png = mxai_client.post(
        "/api/plugins/mxai/materials/assets",
        params={
            "library_id": library_id,
            "access_scope": "local",
        },
        files={"file": ("hero.png", io.BytesIO(b"png-bytes-1"), "image/png")},
    )
    assert png.status_code == 200
    hero = png.json()["item"]
    assert hero["media_kind"] == "image"
    assert hero["preview_kind"] == "image"
    assert hero["access_scope"] == "local"
    assert hero["public_sync_status"] == "none"
    hero_id = hero["asset_id"]

    md = mxai_client.post(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id},
        files={"file": ("note.md", io.BytesIO(b"# hello"), "text/markdown")},
    )
    assert md.status_code == 200
    note = md.json()["item"]
    assert note["media_kind"] == "text"
    assert note["preview_kind"] == "other"
    note_id = note["asset_id"]

    by_kind = mxai_client.get(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id, "media_kind": "text"},
    )
    assert by_kind.status_code == 200
    assert by_kind.json()["total"] == 1
    assert by_kind.json()["items"][0]["asset_id"] == note_id

    by_access = mxai_client.get(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id, "access_scope": "local"},
    )
    assert by_access.status_code == 200
    assert by_access.json()["total"] == 2

    patched = mxai_client.patch(
        f"/api/plugins/mxai/materials/assets/{hero_id}",
        json={"media_kind": "image", "access_scope": "local"},
    )
    assert patched.status_code == 200
    patched_item = patched.json()["item"]
    assert patched_item["media_kind"] == "image"
    assert patched_item["preview_kind"] == "image"

    mxai_client.delete(f"/api/plugins/mxai/materials/assets/{hero_id}")
    mxai_client.delete(f"/api/plugins/mxai/materials/assets/{note_id}")
    mxai_client.delete(f"/api/plugins/mxai/materials/libraries/{library_id}")


def test_media_kind_axes_helpers() -> None:
    from plugins.mxai.materials.axes import (
        media_kind_for,
        media_kind_sql_match,
        preview_kind_from_media,
        resolve_asset_kinds,
        sniff_mime_from_bytes,
    )

    assert media_kind_for("a.wav", "audio/wav") == "audio"
    assert media_kind_for("doc.pdf", "application/pdf") == "document"
    assert media_kind_for("readme.md", None) == "text"
    assert media_kind_for("photo.webp", None) == "image"
    assert media_kind_for("OIP-C.webp_ref-94a26c32", None) == "image"
    assert media_kind_for("OIP-C.webp_ref-94a26c32.webp", None) == "image"
    webp = b"RIFF\x00\x00\x00\x00WEBP"
    assert sniff_mime_from_bytes(webp) == "image/webp"
    assert media_kind_for("upload.bin", None, content=webp) == "image"
    mk, pk, _ = resolve_asset_kinds(
        display_name="OIP-C.webp_ref-94a26c32",
        mime_type=None,
        media_kind="other",
        preview_kind="other",
    )
    assert mk == "image"
    assert pk == "image"
    clause, params = media_kind_sql_match("image")
    assert "media_kind = ?" in clause
    assert "%.webp" in params
    assert preview_kind_from_media("document") == "other"
    assert preview_kind_from_media("video") == "video"
    assert preview_kind_from_media("image") == "image"
