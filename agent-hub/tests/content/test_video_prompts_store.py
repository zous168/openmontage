"""video_prompts_store 单测（VC-T15）。"""

from plugins.mxai.content.video_prompts_store import ensure_seeded, get_meta, publish, restore_factory


def test_seed_and_publish(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    ensure_seeded("viral_clone")
    meta = get_meta("viral_clone")
    assert meta.get("prompt_version")
    pub = publish("viral_clone")
    assert int(pub["prompt_version"]) >= 2


def test_restore_factory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    ensure_seeded("img_text")
    restore_factory("img_text")
    meta = get_meta("img_text")
    assert meta.get("kind") == "img_text"
