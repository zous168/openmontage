"""gen_mode 推断与 r2v media 解析（VC-T06/T07）。"""



from __future__ import annotations



import pytest



from plugins.mxai.content.gen_mode_resolver import (

    build_r2v_media,

    gen_mode_from_model,

    pick_video_model,

    resolve_media_urls,

    resolve_shot_gen_mode,

)





def test_gen_mode_from_model_suffixes() -> None:

    assert gen_mode_from_model("doubao-video-rpa-i2v") == "i2v"

    assert gen_mode_from_model("grok-imagine-t2v") == "t2v"

    assert gen_mode_from_model("mock-r2v-flash") == "r2v"

    assert gen_mode_from_model("doubao-video-rpa") == "t2v"





def test_resolve_shot_gen_mode_explicit() -> None:

    assert resolve_shot_gen_mode({"gen_mode": "r2v"}) == "r2v"





def test_resolve_shot_gen_mode_from_model() -> None:

    assert resolve_shot_gen_mode({"model": "doubao-video-rpa-i2v"}) == "i2v"





def test_resolve_shot_gen_mode_default_t2v() -> None:

    assert resolve_shot_gen_mode({}) == "t2v"

    assert resolve_shot_gen_mode({}, options={"model": "wan-t2v"}) == "t2v"





def test_pick_video_model_hint_in_catalog_used_as_is() -> None:

    catalog = [

        {"model_name": "wan2.1-i2v"},

        {"model_name": "wan2.1-t2v"},

    ]

    assert pick_video_model("t2v", "wan2.1-i2v", catalog) == "wan2.1-i2v"

    assert pick_video_model("i2v", "doubao-video-rpa-i2v", catalog + [{"model_name": "doubao-video-rpa-i2v"}]) == "doubao-video-rpa-i2v"





def test_pick_video_model_stale_hint_falls_back_to_mode() -> None:

    catalog = [

        {"model_name": "mock-t2v"},

        {"model_name": "grok-imagine-t2v"},

        {"model_name": "mock-i2v"},

    ]

    assert pick_video_model("i2v", "stale-not-in-catalog", catalog) == "mock-i2v"





def test_pick_video_model_reads_model_name() -> None:

    """网关目录字段是 model_name，不是 id。"""

    catalog = [{"model_name": "mock-t2v", "mode": "video_generation"}]

    assert pick_video_model("t2v", None, catalog) == "mock-t2v"





def test_pick_video_model_t2v_no_match_raises() -> None:

    with pytest.raises(ValueError, match="VC_GEN_MODEL_MATCH_FAILED"):

        pick_video_model("t2v", None, [{"model_name": "some-llm-chat"}])





def test_build_r2v_media_respects_ref_ids_order() -> None:

    params = {

        "refs": [

            {"id": "p1", "url": "https://cdn/p1.jpg"},

            {"id": "p2", "url": "https://cdn/p2.jpg"},

        ],

    }

    media = build_r2v_media({"ref_ids": ["p2", "p1"]}, params)

    assert [x.get("ref_id") for x in media] == ["p2", "p1"]

    assert media[0]["url"] == "https://cdn/p2.jpg"





def test_resolve_ref_ids() -> None:

    params = {"refs": [{"id": "p1", "url": "https://cdn/p1.jpg"}]}

    media = build_r2v_media({"ref_ids": ["p1"]}, params)

    resolved = resolve_media_urls(media, params=params)

    assert len(resolved) == 1

    assert resolved[0]["url"] == "https://cdn/p1.jpg"





def test_resolve_key_assets_replace_image_url() -> None:

    key_assets = [{"id": "prod", "replace_image_url": "https://cdn/replace.jpg"}]

    media = [{"type": "reference_image", "ref_id": "prod"}]

    resolved = resolve_media_urls(media, params={}, key_assets=key_assets)

    assert len(resolved) == 1

    assert resolved[0]["url"] == "https://cdn/replace.jpg"

