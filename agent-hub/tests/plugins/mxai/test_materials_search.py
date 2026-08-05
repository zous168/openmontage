"""素材库组合检索（关键词 / 名称 / 标签 / top_k）."""

from __future__ import annotations

import json

import pytest

from plugins.mxai.materials.service import search_assets, upload_asset


@pytest.fixture
def materials_search_env(mxai_env):
    del mxai_env
    yield


def _seed_library(data_dir=None) -> tuple[int, list[int]]:
    from plugins.mxai.materials.service import create_library

    lib = create_library("检索测试库", data_dir)
    library_id = int(lib["library_id"])
    ids: list[int] = []
    for filename, tags in (
        ("产品主图-hero.png", ["产品图", "banner"]),
        ("微信客服二维码.jpg", ["微信", "二维码"]),
        ("宣传册封面.pdf", ["产品图", "宣传"]),
    ):
        item = upload_asset(
            library_id=library_id,
            filename=filename,
            content=f"bytes-{filename}".encode(),
            tags=tags,
            data_dir=data_dir,
        )
        ids.append(int(item["asset_id"]))
    return library_id, ids


def test_search_by_keyword(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(library_id=library_id, query="微信")
    assert out["total"] == 1
    assert out["items"][0]["display_name"].endswith("二维码.jpg")


def test_search_by_name_partial(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(library_id=library_id, name="主图")
    assert out["total"] == 1
    assert "hero" in out["items"][0]["display_name"]


def test_search_by_tag_any(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(library_id=library_id, tags=["产品图"], tag_match="any")
    assert out["total"] == 2


def test_search_by_tag_all(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(library_id=library_id, tags=["产品图", "banner"], tag_match="all")
    assert out["total"] == 1
    assert "hero" in out["items"][0]["display_name"]


def test_update_asset_tags_add_remove(materials_search_env) -> None:
    library_id, ids = _seed_library()
    asset_id = ids[0]
    from plugins.mxai.materials.service import get_asset, update_asset_tags

    tagged = update_asset_tags(asset_id, ["新标签"], mode="add")
    assert "新标签" in tagged["tags"]
    assert "产品图" in tagged["tags"]

    search = search_assets(library_id=library_id, tags=["新标签"])
    assert search["total"] >= 1

    stripped = update_asset_tags(asset_id, ["新标签"], mode="remove")
    assert "新标签" not in stripped["tags"]
    assert get_asset(asset_id)["tags"] == stripped["tags"]


def test_search_top_k(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(library_id=library_id, top_k=2)
    assert out["total"] == 3
    assert len(out["items"]) == 2
    assert out["top_k"] == 2


def test_search_combined_filters(materials_search_env) -> None:
    library_id, _ = _seed_library()
    out = search_assets(
        library_id=library_id,
        query="产品",
        tags=["宣传"],
        tag_match="all",
        top_k=1,
    )
    assert out["total"] == 1
    assert len(out["items"]) == 1
    assert out["items"][0]["display_name"].endswith("封面.pdf")


def test_mxai_materials_search_tool_top_k_and_tags(mxai_env) -> None:
    from plugins.mxai.mcp_tools import _handle_materials_save, _handle_materials_search

    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_path = cache_dir / "img_tagsearch01.jpg"
    img_path.write_bytes(b"\xff\xd8\xff" + b"a" * 32)

    saved = json.loads(
        _handle_materials_save(
            {
                "file_path": str(img_path),
                "display_name": "春季促销海报.jpg",
                "tags": ["促销", "海报"],
            }
        )
    )
    lib_id = saved["library_id"]

    by_tag = json.loads(
        _handle_materials_search(
            {"library_id": lib_id, "tags": ["促销"], "top_k": 5}
        )
    )
    assert by_tag["count"] >= 1
    assert by_tag["top_k"] == 5

    by_name = json.loads(
        _handle_materials_search({"library_id": lib_id, "name": "春季", "top_k": 1})
    )
    assert by_name["count"] == 1
