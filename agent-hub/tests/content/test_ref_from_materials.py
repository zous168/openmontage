"""从素材库选用参考图。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from plugins.mxai.content.ref_upload import create_ref_from_materials


def test_create_ref_from_materials_reuses_synced_public_url():
    asset = {
        "asset_id": 7,
        "display_name": "hero.webp",
        "preview_kind": "image",
        "media_kind": "image",
        "public_url": "https://cdn.example/mat/7.webp",
        "oss_key": "mat/7.webp",
        "public_sync_status": "synced",
    }
    with patch("plugins.mxai.materials.service.get_asset", return_value=asset):
        item = create_ref_from_materials(7, role="product", label="产品图")

    assert item["url"] == "https://cdn.example/mat/7.webp"
    assert item["materials_asset_id"] == 7
    assert item["source"] == "materials"
    assert item["role"] == "product"


def test_create_ref_from_materials_uploads_local_file(tmp_path: Path):
    img = tmp_path / "cup.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    asset = {
        "asset_id": 9,
        "display_name": "cup.png",
        "preview_kind": "image",
        "media_kind": "image",
        "mime_type": "image/png",
        "public_sync_status": "none",
    }
    with (
        patch("plugins.mxai.materials.service.get_asset", return_value=asset),
        patch("plugins.mxai.materials.service.resolve_asset_path", return_value=img),
        patch(
            "plugins.mxai.content.ref_upload._upload_bytes_to_public_url",
            return_value=("https://cdn.example/uploads/9.png", "uploads/9.png"),
        ) as upload_mock,
    ):
        item = create_ref_from_materials(9, role="character")

    upload_mock.assert_called_once()
    assert item["url"] == "https://cdn.example/uploads/9.png"
    assert item["materials_asset_id"] == 9
    assert item["role"] == "character"
    assert "sha256" in item


def test_create_ref_from_materials_rejects_non_image():
    asset = {
        "asset_id": 3,
        "display_name": "note.md",
        "preview_kind": "other",
        "media_kind": "text",
    }
    with patch("plugins.mxai.materials.service.get_asset", return_value=asset):
        with pytest.raises(HTTPException) as ei:
            create_ref_from_materials(3)
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "VC_REF_NOT_IMAGE"
