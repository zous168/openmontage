"""LT-026 materials API tests."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def test_materials_library_folder_upload_search(mxai_client: TestClient) -> None:
    lib = mxai_client.post(
        "/api/plugins/mxai/materials/libraries",
        json={"name": "测试素材库"},
    )
    assert lib.status_code == 200
    library_id = lib.json()["item"]["library_id"]

    folder = mxai_client.post(
        f"/api/plugins/mxai/materials/libraries/{library_id}/folders",
        json={"name": "产品图"},
    )
    assert folder.status_code == 200
    folder_id = folder.json()["item"]["folder_id"]

    content = b"fake-png-bytes"
    up = mxai_client.post(
        "/api/plugins/mxai/materials/assets",
        params={
            "library_id": library_id,
            "folder_id": folder_id,
            "tags": "banner,hero",
        },
        files={"file": ("hero.png", io.BytesIO(content), "image/png")},
    )
    assert up.status_code == 200
    asset_id = up.json()["item"]["asset_id"]
    assert "banner" in up.json()["item"]["tags"]

    dup = mxai_client.post(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id, "folder_id": folder_id},
        files={"file": ("hero.png", io.BytesIO(content), "image/png")},
    )
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "MAT_DUPLICATE_CONTENT"

    search = mxai_client.get(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id, "q": "banner"},
    )
    assert search.status_code == 200
    assert search.json()["total"] >= 1
    assert any(i["asset_id"] == asset_id for i in search.json()["items"])

    by_name = mxai_client.get(
        "/api/plugins/mxai/materials/assets",
        params={"library_id": library_id, "q": "hero"},
    )
    assert by_name.status_code == 200
    assert by_name.json()["total"] >= 1

    preview = mxai_client.get(f"/api/plugins/mxai/materials/assets/{asset_id}/preview")
    assert preview.status_code == 200

    mxai_client.delete(f"/api/plugins/mxai/materials/assets/{asset_id}")
    mxai_client.delete(f"/api/plugins/mxai/materials/folders/{folder_id}")
    mxai_client.delete(f"/api/plugins/mxai/materials/libraries/{library_id}")
