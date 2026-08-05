"""批量添加模板本机落盘（按渠道隔离）."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.contacts.pending_add_local_exports import (
    list_templates,
    normalize_profile,
    pending_add_template_dir,
    resolve_template_file,
    save_template_bytes,
    template_filename,
)
from plugins.mxai.contacts.pending_add_template import build_pending_add_template_xlsx


def test_normalize_profile_rejects_other() -> None:
    with pytest.raises(ValueError):
        normalize_profile("douyin")


def test_save_and_list_isolated_by_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    wx = build_pending_add_template_xlsx("wechat")
    qw = build_pending_add_template_xlsx("qiyeweixin")
    saved_wx = save_template_bytes("wechat", wx)
    saved_qw = save_template_bytes("qiyeweixin", qw)

    assert saved_wx["profile_id"] == "wechat"
    assert saved_qw["profile_id"] == "qiyeweixin"
    assert Path(saved_wx["dir"]).name == "wechat"
    assert Path(saved_qw["dir"]).name == "qiyeweixin"
    assert saved_wx["name"] == template_filename("wechat")
    assert saved_qw["name"] == template_filename("qiyeweixin")
    assert "批量添加模板" in saved_wx["dir"]

    listed_wx = list_templates("wechat")
    listed_qw = list_templates("qiyeweixin")
    assert [i["name"] for i in listed_wx["items"]] == [template_filename("wechat")]
    assert [i["name"] for i in listed_qw["items"]] == [template_filename("qiyeweixin")]
    assert listed_wx["dir"] != listed_qw["dir"]

    path = resolve_template_file("wechat", template_filename("wechat"))
    assert path.is_file()
    assert path.read_bytes()[:2] == b"PK"

    with pytest.raises(LookupError):
        resolve_template_file("wechat", template_filename("qiyeweixin"))


def test_dir_path_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    d = pending_add_template_dir("wechat")
    assert d.as_posix().endswith("Documents/MxAI/批量添加模板/wechat") or str(d).endswith(
        str(Path("Documents") / "MxAI" / "批量添加模板" / "wechat")
    )
