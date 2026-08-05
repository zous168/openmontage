"""创作项目 → 素材库最终产物归档."""

from __future__ import annotations

import pytest

from plugins.mxai.content.create_history import KIND_IMG_TEXT, KIND_VIRAL_CLONE
from plugins.mxai.content.create_materials_archive import (
    CREATE_LIBRARY_NAME,
    archive_bytes,
    archive_session_final,
    ensure_create_library,
    ensure_project_tree,
)
from plugins.mxai.materials.service import list_assets, list_folders, list_libraries


def test_ensure_create_library_idempotent(mxai_env) -> None:
    del mxai_env
    a = ensure_create_library()
    b = ensure_create_library()
    assert a == b
    libs = list_libraries()
    assert any(lib["name"] == CREATE_LIBRARY_NAME for lib in libs)


def test_ensure_project_tree_structure(mxai_env) -> None:
    del mxai_env
    tree = ensure_project_tree(
        kind=KIND_IMG_TEXT,
        session_id="556edc73-2342-4fa1-abcc-955429bb7c4b",
        title="测试图文项目",
    )
    assert tree["library_id"] > 0
    assert tree["project_folder_id"] > 0
    assert tree.get("folder_ids") == {}

    folders = list_folders(tree["library_id"])
    names = {f["name"] for f in folders}
    assert "图文视频" in names
    assert "refs" not in names
    assert "shots" not in names

    tree2 = ensure_project_tree(
        kind=KIND_IMG_TEXT,
        session_id="556edc73-2342-4fa1-abcc-955429bb7c4b",
        title="测试图文项目",
    )
    assert tree2["project_folder_id"] == tree["project_folder_id"]
    assert len(list_folders(tree["library_id"])) == len(folders)


def test_archive_session_final_requires_compose(mxai_env) -> None:
    del mxai_env
    item = {
        "id": "f87d58b3-c23f-45d7-85ae-538ed87cc04f",
        "kind": KIND_VIRAL_CLONE,
        "title": "仿爆款_f87d58b3",
        "shots": [{"id": "1", "video_url": "https://example.com/shot1.mp4"}],
    }
    with pytest.raises(ValueError, match="剪辑合成"):
        archive_session_final(item)


def test_archive_session_final_archives_shots_and_skips_duplicate(mxai_env, tmp_path) -> None:
    del mxai_env
    shot_file = tmp_path / "shot_1.mp4"
    shot_file.write_bytes(b"fake-video-bytes")
    item = {
        "id": "f87d58b3-c23f-45d7-85ae-538ed87cc04f",
        "kind": KIND_VIRAL_CLONE,
        "title": "仿爆款_f87d58b3",
        "stage": "composed",
        "legacy_step_raw": {
            "compose": {
                "draft_name": "test.draft",
            }
        },
        "shots": [
            {
                "id": "1",
                "video_url": str(shot_file),
            }
        ],
    }

    materials = archive_session_final(item)
    assert item.get("materials")
    assert materials["archived_count"] >= 1
    assert materials.get("archived_at")

    lib_id = materials["library_id"]
    project_folder = materials["project_folder_id"]
    listed = list_assets(library_id=lib_id, folder_id=project_folder)
    assert listed["total"] >= 1

    payload = b"fake-video-bytes"
    first = archive_bytes(
        payload,
        filename="shot_1.mp4",
        library_id=lib_id,
        folder_id=project_folder,
        kind=KIND_VIRAL_CLONE,
        session_id=item["id"],
        role="final",
    )
    assert first and first.get("asset_id")
    second = archive_bytes(
        payload,
        filename="shot_1_copy.mp4",
        library_id=lib_id,
        folder_id=project_folder,
        kind=KIND_VIRAL_CLONE,
        session_id=item["id"],
        role="final",
    )
    assert second
    assert second.get("duplicate_skipped") or second["asset_id"] == first["asset_id"]
