"""参考图归档至素材库."""

from __future__ import annotations

from plugins.mxai.content.create_history import KIND_IMG_TEXT
from plugins.mxai.content.create_materials_archive import archive_ref_upload
from plugins.mxai.materials.service import list_assets


def test_archive_ref_upload(mxai_env) -> None:
    del mxai_env
    content = b"\x89PNG\r\n\x1a\n" + b"x" * 16
    asset = archive_ref_upload(
        content,
        filename="cup.png",
        kind=KIND_IMG_TEXT,
        session_id="556edc73-2342-4fa1-abcc-955429bb7c4b",
        title="玻璃杯子",
        ref_id="ref-abc",
        label="产品图",
    )
    assert asset and asset.get("asset_id")
    listed = list_assets(library_id=asset["library_id"], folder_id=asset.get("folder_id"))
    assert listed["total"] >= 1
