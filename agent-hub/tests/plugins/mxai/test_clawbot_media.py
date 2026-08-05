"""ClawBot 入站图片标记与缓存解析."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.media import (
    chat_image_spec_from_path,
    image_marker_from_cache_path,
    material_preview_marker,
    material_preview_url,
    resolve_cached_image,
    strip_image_markers,
    strip_media_markers,
)


def test_strip_image_markers() -> None:
    raw = "[微信] hi\n[mxai-image:img_aabbccddeeff.jpg]"
    plain, names = strip_image_markers(raw)
    assert names == ["img_aabbccddeeff.jpg"]
    assert "[mxai-image" not in plain
    assert "hi" in plain


def test_resolve_cached_image(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "gateway.platforms.base.get_image_cache_dir",
        lambda: tmp_path,
    )
    img = tmp_path / "img_test12345678.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"x" * 32)
    assert resolve_cached_image("img_test12345678.jpg") == img
    assert resolve_cached_image("../evil.jpg") is None
    assert image_marker_from_cache_path(str(img)) == "[mxai-image:img_test12345678.jpg]"


def test_material_preview_marker_and_strip_media_markers() -> None:
    marker = material_preview_marker(42)
    assert marker == "[mxai-material:42]"
    assert material_preview_url(42).endswith("/assets/42/preview")
    plain, images = strip_media_markers(f"请看\n{marker}")
    assert "[mxai-material" not in plain
    assert images
    assert images[0]["asset_id"] == "42"
    assert "42/preview" in images[0]["url"]


def test_generated_image_marker_and_media_strip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "gateway.platforms.base.get_image_cache_dir",
        lambda: tmp_path,
    )
    img = tmp_path / "image_20260302_120000_abcd1234.png"
    img.write_bytes(b"\x89PNG\r\n" + b"x" * 32)
    marker = image_marker_from_cache_path(str(img))
    assert marker == "[mxai-image:image_20260302_120000_abcd1234.png]"
    plain, images = strip_media_markers(f"生成好了\n{marker}\nMEDIA:{img}")
    assert "MEDIA:" not in plain
    assert "[mxai-image" not in plain
    assert images
    assert images[0]["name"] == "image_20260302_120000_abcd1234.png"
    assert chat_image_spec_from_path(str(img)) is not None


def test_local_preview_outside_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.media._allowed_local_preview_roots",
        lambda: [tmp_path.resolve()],
    )
    img = tmp_path / "Background.png"
    img.write_bytes(b"\x89PNG\r\n" + b"x" * 16)
    spec = chat_image_spec_from_path(str(img))
    assert spec is not None
    assert "local-preview" in spec["url"]
    plain, images = strip_media_markers(f"请看\nMEDIA:{img}")
    assert images
    assert images[0]["name"] == "Background.png"
