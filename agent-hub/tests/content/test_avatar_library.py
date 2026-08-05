"""数字人形象库 mock 测试 (LT-054)。

覆盖：mock 预设、avatar_presets.json 系统预设读取、用户形象（素材库 avatar 标签派生）、
register_avatar 打标签、media_kind 映射、REST 冒烟。
"""

from __future__ import annotations

from plugins.mxai.api.content import get_avatars, post_avatar_register
from plugins.mxai.content.avatar_library import (
    _load_presets,
    avatar_media_dir,
    list_avatars,
    register_avatar,
    resolve_avatar_media_path,
)
from plugins.mxai.materials.service import create_library, get_asset, upload_asset


def _env(tmp_path, monkeypatch, mock: bool = True) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MXAI_MOCK", "1" if mock else "0")


# ============================================================================
# mock 模式
# ============================================================================

def test_mock_mode_has_no_preset_avatars(tmp_path, monkeypatch) -> None:
    """数字人为真实功能（非 mock）：mock 模式下无 avatar_presets.json → system 空态。"""
    _env(tmp_path, monkeypatch)
    resp = list_avatars()
    assert resp["mock"] is True
    assert resp["system"] == []
    assert resp["user"] == []
    assert resp["items"] == []


def test_mock_mode_user_avatars_real_from_materials(tmp_path, monkeypatch) -> None:
    """mock 模式下「我的形象」仍从素材库真实派生（素材库无 mock，任何模式真实可用）。"""
    _env(tmp_path, monkeypatch)
    from plugins.mxai.materials.service import create_library, upload_asset

    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="host.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = register_avatar(int(asset["asset_id"]), name="我的主播")
    assert item["source"] == "user"
    resp = list_avatars()
    assert [a["id"] for a in resp["user"]] == [item["id"]]
    assert resp["system"] == []


def test_ensure_avatar_materials_library_is_dedicated(tmp_path, monkeypatch) -> None:
    """上传目标库固定「数字人形象」，不复用音色首个分库。"""
    from plugins.mxai.content.avatar_library import (
        _AVATAR_LIBRARY_NAME,
        _ensure_materials_library_id,
    )
    from plugins.mxai.materials.service import create_library, get_library

    _env(tmp_path, monkeypatch, mock=False)
    create_library("声音素材")
    create_library("创作")
    lid = _ensure_materials_library_id()
    lib = get_library(lid)
    assert lib["name"] == _AVATAR_LIBRARY_NAME
    # 再次调用应复用同一库，不重复创建
    assert _ensure_materials_library_id() == lid


# ============================================================================
# avatar_presets.json 系统预设
# ============================================================================

def test_load_presets_missing_file_returns_empty(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    assert _load_presets() == []


def test_load_presets_reads_json(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    state_dir = tmp_path / "plugins" / "mxai"
    (state_dir / "content").mkdir(parents=True, exist_ok=True)
    # plugin_state_dir 实际路径以 cfg.paths 为准；从 _presets_path() 落盘
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        '{"items": [{"id": "sys_female", "name": "主播女", "media_kind": "video",'
        ' "url": "https://cdn.example.com/avatar.mp4"}]}',
        encoding="utf-8",
    )
    presets = _load_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "sys_female"
    assert presets[0]["source"] == "system"
    assert presets[0]["media_kind"] == "video"


def test_list_avatars_non_mock_merges_presets_and_user(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        '{"items": [{"id": "sys_a", "name": "预设A", "url": "https://cdn.example.com/a.jpg"}]}',
        encoding="utf-8",
    )
    resp = list_avatars()
    assert resp["mock"] is False
    assert [a["id"] for a in resp["system"]] == ["sys_a"]
    assert resp["user"] == []


# ============================================================================
# register_avatar — 素材库派生「我的形象」
# ============================================================================

def test_register_avatar_tags_material_and_appears_in_user(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    lib_id = int(lib["library_id"])
    # 上传一张图片素材（png 头）
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    asset = upload_asset(
        library_id=lib_id, filename="avatar.png", content=png, media_kind="image",
    )
    aid = int(asset["asset_id"])

    item = register_avatar(aid, name="我的主播")
    assert item["id"] == f"mat_{aid}"
    assert item["name"] == "我的主播"
    assert item["media_kind"] == "image"
    assert item["mat_asset_id"] == aid
    assert "avatar" in (get_asset(aid).get("tags") or [])

    resp = list_avatars()
    assert [a["id"] for a in resp["user"]] == [f"mat_{aid}"]
    assert resp["items"]


def test_register_avatar_video_media_kind_mapped(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    lib_id = int(lib["library_id"])
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
    asset = upload_asset(
        library_id=lib_id, filename="avatar.mp4", content=mp4, media_kind="video",
    )
    item = register_avatar(int(asset["asset_id"]))
    assert item["media_kind"] == "video"
    assert item["url"].startswith("/api/plugins/mxai/materials/assets/")


def test_register_avatar_unknown_asset_rejected(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    from fastapi import HTTPException

    try:
        register_avatar(99999)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected HTTPException 404")


# ============================================================================
# 本地媒体（avatar_media 静态服务 + 路径穿越防护）
# ============================================================================

def test_resolve_avatar_media_path_and_traversal_guard(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    from fastapi import HTTPException

    d = avatar_media_dir()
    (d / "kara.mp4").write_bytes(b"fake-mp4")
    path = resolve_avatar_media_path("kara.mp4")
    assert path.is_file() and path.name == "kara.mp4"
    # 路径穿越防护
    for bad in ("../voice_library.json", "..%2Fetc%2Fpasswd", "", "."):
        try:
            resolve_avatar_media_path(bad)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError(f"expected 404 for {bad!r}")


def test_ensure_public_image_url_local_avatar_media(tmp_path, monkeypatch) -> None:
    """本地 /content/avatar-media/ 参考图 → 读文件上传 OSS 转公网（形象锁定供 LLM 网关拉取）。"""
    _env(tmp_path, monkeypatch)
    from plugins.mxai.content.ref_upload import ensure_public_image_url

    d = avatar_media_dir()
    (d / "kara.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)

    captured: dict = {}

    def fake_upload(data, *, ext):
        captured["ext"] = ext
        return "https://oss.example.com/kara.jpg", "oss/key"

    monkeypatch.setattr("plugins.mxai.content.ref_upload._upload_bytes_to_public_url", fake_upload)
    url = ensure_public_image_url("/content/avatar-media/kara.jpg")
    assert url == "https://oss.example.com/kara.jpg"
    assert captured["ext"] == "jpg"


# ============================================================================
# REST 冒烟
# ============================================================================

def test_rest_get_avatars_mock_mode(tmp_path, monkeypatch) -> None:
    """REST 冒烟：mock 模式下 GET /avatars 返回真实逻辑（presets json 驱动 system）。"""
    _env(tmp_path, monkeypatch)
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        '{"items": [{"id": "sys_a", "name": "预设A", "url": "https://cdn.example.com/a.jpg"}]}',
        encoding="utf-8",
    )
    resp = get_avatars()
    assert resp["mock"] is True
    assert [a["id"] for a in resp["system"]] == ["sys_a"]


def test_rest_register_avatar_route(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    lib_id = int(lib["library_id"])
    asset = upload_asset(
        library_id=lib_id, filename="host.png", content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = post_avatar_register(
        type("Body", (), {"mat_asset_id": int(asset["asset_id"]), "name": "主播B"})()
    )
    assert item["name"] == "主播B"
    assert item["source"] == "user"
    assert item["enabled"] is True


# ============================================================================
# 覆盖层 CRUD（重命名 / 启停 / 删除）
# ============================================================================

def test_rename_avatar_persists_via_override(tmp_path, monkeypatch) -> None:
    from plugins.mxai.content.avatar_library import rename_avatar

    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="a.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = register_avatar(int(asset["asset_id"]), name="旧名")
    renamed = rename_avatar(item["id"], "新主播")
    assert renamed["name"] == "新主播"
    assert renamed["enabled"] is True
    listed = list_avatars()
    assert listed["user"][0]["name"] == "新主播"


def test_rename_avatar_empty_name_rejected(tmp_path, monkeypatch) -> None:
    from fastapi import HTTPException
    from plugins.mxai.content.avatar_library import rename_avatar

    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="a.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = register_avatar(int(asset["asset_id"]))
    try:
        rename_avatar(item["id"], "  ")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail["code"] == "AVATAR_NAME_REQUIRED"
    else:
        raise AssertionError("expected 422")


def test_set_avatar_enabled_false_in_list(tmp_path, monkeypatch) -> None:
    from plugins.mxai.content.avatar_library import set_avatar_enabled

    _env(tmp_path, monkeypatch, mock=False)
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        '{"items": [{"id": "sys_a", "name": "预设A", "url": "https://cdn.example.com/a.jpg"}]}',
        encoding="utf-8",
    )
    out = set_avatar_enabled("sys_a", False)
    assert out["enabled"] is False
    listed = list_avatars()
    assert listed["system"][0]["enabled"] is False
    assert listed["system"][0]["id"] == "sys_a"


def test_delete_user_avatar_removes_tag(tmp_path, monkeypatch) -> None:
    from plugins.mxai.content.avatar_library import delete_avatar

    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="a.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    aid = int(asset["asset_id"])
    item = register_avatar(aid, name="可删")
    assert "avatar" in (get_asset(aid).get("tags") or [])
    res = delete_avatar(item["id"])
    assert res["ok"] is True
    assert "avatar" not in (get_asset(aid).get("tags") or [])
    assert list_avatars()["user"] == []


def test_delete_system_avatar_rejected(tmp_path, monkeypatch) -> None:
    from fastapi import HTTPException
    from plugins.mxai.content.avatar_library import delete_avatar

    _env(tmp_path, monkeypatch, mock=False)
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().parent.mkdir(parents=True, exist_ok=True)
    _presets_path().write_text(
        '{"items": [{"id": "sys_a", "name": "预设A", "url": "https://cdn.example.com/a.jpg"}]}',
        encoding="utf-8",
    )
    try:
        delete_avatar("sys_a")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail["code"] == "SYSTEM_AVATAR"
    else:
        raise AssertionError("expected 422")


def test_delete_clears_override_entry(tmp_path, monkeypatch) -> None:
    from plugins.mxai.content.avatar_library import (
        _overrides_path,
        _read_overrides,
        delete_avatar,
        rename_avatar,
    )

    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="a.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = register_avatar(int(asset["asset_id"]), name="初名")
    rename_avatar(item["id"], "覆盖名")
    assert item["id"] in _read_overrides()
    delete_avatar(item["id"])
    assert item["id"] not in _read_overrides()
    # 覆盖层文件仍存在但条目已清
    assert _overrides_path().is_file()


def test_overrides_corrupt_file_degrades_empty(tmp_path, monkeypatch) -> None:
    from plugins.mxai.content.avatar_library import _overrides_path, _read_overrides

    _env(tmp_path, monkeypatch, mock=False)
    path = _overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    assert _read_overrides() == {}
    # list 仍可用（默认 enabled）
    from plugins.mxai.content.avatar_library import _presets_path

    _presets_path().write_text(
        '{"items": [{"id": "sys_a", "name": "预设A", "url": "https://cdn.example.com/a.jpg"}]}',
        encoding="utf-8",
    )
    resp = list_avatars()
    assert resp["system"][0]["enabled"] is True


def test_rest_patch_and_delete_avatar_routes(tmp_path, monkeypatch) -> None:
    from plugins.mxai.api.content import (
        AvatarUpdateBody,
        delete_avatar_item,
        patch_avatar_item,
    )

    _env(tmp_path, monkeypatch, mock=False)
    lib = create_library("形象库")
    asset = upload_asset(
        library_id=int(lib["library_id"]),
        filename="host.png",
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        media_kind="image",
    )
    item = register_avatar(int(asset["asset_id"]), name="主播")
    patched = patch_avatar_item(item["id"], AvatarUpdateBody(name="新名", enabled=False))
    assert patched["name"] == "新名"
    assert patched["enabled"] is False
    deleted = delete_avatar_item(item["id"])
    assert deleted["ok"] is True

