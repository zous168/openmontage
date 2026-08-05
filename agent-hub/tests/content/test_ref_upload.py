"""参考图 OSS 上传（public_url）。"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import HTTPException, UploadFile

from plugins.mxai.content.ref_upload import (
    _safe_ext,
    ensure_public_image_url,
    upload_create_ref_image,
)


def test_safe_ext_from_filename():
    assert _safe_ext("a.PNG", None) == "png"
    assert _safe_ext("x.jpeg", "image/jpeg") == "jpg"


def test_ensure_public_image_url_passthrough_https():
    assert (
        ensure_public_image_url("https://cdn.example/a.jpg")
        == "https://cdn.example/a.jpg"
    )


def test_ensure_public_image_url_uploads_data_url():
    raw = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    import base64

    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    with patch(
        "plugins.mxai.content.ref_upload._upload_bytes_to_public_url",
        return_value=("https://cdn.example/uploads/f.png", "uploads/f.png"),
    ) as up:
        out = ensure_public_image_url(data_url)
    assert out == "https://cdn.example/uploads/f.png"
    up.assert_called_once()
    assert up.call_args.kwargs["ext"] == "png"


def test_safe_ext_rejects_unknown():
    with pytest.raises(HTTPException) as ei:
        _safe_ext("a.txt", "text/plain")
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_upload_create_ref_image_returns_public_url():
    raw = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    upload = UploadFile(filename="cup.png", file=BytesIO(raw))

    with (
        patch(
            "plugins.mxai.content.ref_upload._upload_bytes_to_public_url",
            return_value=("https://cdn.example/uploads/t/1.png", "uploads/t/1.png"),
        ),
    ):
        item = await upload_create_ref_image(upload, role="product", label="杯子")

    assert item["url"] == "https://cdn.example/uploads/t/1.png"
    assert item["oss_key"] == "uploads/t/1.png"
    assert item["role"] == "product"
    assert item["source"] == "upload"
    assert item["enabled"] is True
    assert item["id"].startswith("ref-")
    assert "sha256" in item
    assert len(item["sha256"]) == 64
    assert "materials_asset_id" not in item


@pytest.mark.asyncio
async def test_upload_create_ref_image_archives_when_session_given():
    raw = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    upload = UploadFile(filename="cup.png", file=BytesIO(raw))

    with (
        patch(
            "plugins.mxai.content.ref_upload._upload_bytes_to_public_url",
            return_value=("https://cdn.example/uploads/t/1.png", "uploads/t/1.png"),
        ),
        patch(
            "plugins.mxai.content.create_materials_archive.archive_ref_upload",
            return_value={"asset_id": 42},
        ) as archive_mock,
    ):
        item = await upload_create_ref_image(
            upload,
            role="product",
            label="杯子",
            session_id="556edc73-2342-4fa1-abcc-955429bb7c4b",
            kind="img_text",
            title="玻璃杯子",
        )

    assert item["materials_asset_id"] == 42
    archive_mock.assert_called_once()


@pytest.mark.asyncio
async def test_upload_empty_rejected():
    upload = UploadFile(filename="a.png", file=BytesIO(b""))
    with pytest.raises(HTTPException) as ei:
        await upload_create_ref_image(upload)
    assert ei.value.status_code == 422
