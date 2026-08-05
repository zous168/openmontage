"""copy_continuity 单测（VC-T13）。"""

from plugins.mxai.content.copy_continuity import validate_copy_continuity


def test_copy_ok() -> None:
    shots = [{"copy": "你好"}, {"copy": "世界"}]
    assert validate_copy_continuity(shots)["ok"] is True


def test_copy_gap() -> None:
    shots = [{"copy": "你好"}, {"copy": "", "has_voice": True}]
    r = validate_copy_continuity(shots)
    assert r["ok"] is False
    assert r["gaps"][0]["index"] == 1


def test_broll_skip() -> None:
    shots = [{"has_voice": False, "prompt": "x"}]
    assert validate_copy_continuity(shots)["ok"] is True


def test_prompt_only_skip() -> None:
    shots = [{"prompt": "产品特写", "copy": ""}]
    assert validate_copy_continuity(shots)["ok"] is True
