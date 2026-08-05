"""Offline behavior tests for ZhipuImage.execute().

Monkeypatches requests.post/get with fake responses — no real API calls
and no real key required.

Run: pytest tests/tools/test_zhipu_image_execute.py -v
"""

import pytest


class FakeResp:
    """Stand-in for requests.Response with the fields the tool uses."""

    def __init__(self, payload, content=b""):
        self._payload = payload
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _api_response(urls, content_filter=None):
    data = {
        "created": 1,
        "data": [{"url": url} for url in urls],
    }
    if content_filter is not None:
        data["content_filter"] = content_filter
    return data


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "fake-key-for-testing")


class TestExecuteSuccess:

    def test_generates_and_downloads_image(self, monkeypatch, tmp_path):
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: FakeResp(_api_response(["https://x/img.png"])),
        )
        monkeypatch.setattr(
            requests, "get",
            lambda url, **kw: FakeResp({}, content=b"img-bytes"),
        )

        out = tmp_path / "shot.png"
        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({
            "prompt": "一只橘猫", "output_path": str(out),
        })

        assert result.success is True
        assert result.data["provider"] == "zhipu"
        assert result.data["model"] == "cogview-4-250304"
        assert result.data["size"] == "1024x1024"
        assert result.data["quality"] == "standard"
        assert result.data["images_generated"] == 1
        assert result.artifacts == [str(out)]
        assert out.exists()
        assert out.read_bytes() == b"img-bytes"

    def test_passes_overrides_to_payload(self, monkeypatch, tmp_path):
        import requests

        captured = {}

        def fake_post(url, **kw):
            captured["json"] = kw.get("json", {})
            return FakeResp(_api_response(["https://x/img.png"]))

        monkeypatch.setattr(requests, "post", fake_post)
        monkeypatch.setattr(
            requests, "get",
            lambda url, **kw: FakeResp({}, content=b"x"),
        )

        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({
            "prompt": "海报", "model": "cogview-3-flash",
            "quality": "hd", "size": "1344x768",
            "watermark_enabled": False, "user_id": "user-1",
            "output_path": str(tmp_path / "s.png"),
        })

        assert result.success is True
        payload = captured["json"]
        assert payload["model"] == "cogview-3-flash"
        assert payload["quality"] == "hd"
        assert payload["size"] == "1344x768"
        assert payload["watermark_enabled"] is False
        assert payload["user_id"] == "user-1"

    def test_content_filter_passthrough(self, monkeypatch, tmp_path):
        import requests

        content_filter = {"role": "assistant", "level": 2}
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: FakeResp(
                _api_response(["https://x/img.png"], content_filter=content_filter)
            ),
        )
        monkeypatch.setattr(
            requests, "get",
            lambda url, **kw: FakeResp({}, content=b"x"),
        )

        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({
            "prompt": "test", "output_path": str(tmp_path / "s.png"),
        })

        assert result.success is True
        assert result.data["content_filter"] == content_filter

    def test_multiple_urls_defensive_download(self, monkeypatch, tmp_path):
        """The API returns one image per call today, but if data[] ever
        carries more than one URL, every image must be saved (no silent
        single-image drop)."""
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: FakeResp(
                _api_response(["https://x/1.png", "https://x/2.png"])
            ),
        )
        monkeypatch.setattr(
            requests, "get",
            lambda url, **kw: FakeResp({}, content=f"img-{url}".encode()),
        )

        out = tmp_path / "shot.png"
        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({
            "prompt": "test", "output_path": str(out),
        })

        assert result.success is True
        assert result.data["images_generated"] == 2
        assert len(result.artifacts) == 2
        assert (tmp_path / "shot_1.png").exists()
        assert (tmp_path / "shot_2.png").exists()
        assert (tmp_path / "shot_1.png").read_bytes() == b"img-https://x/1.png"


class TestExecuteFailures:

    def test_no_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({"prompt": "test"})
        assert result.success is False
        assert "ZHIPU_API_KEY" in result.error
        assert "bigmodel.cn" in result.error

    def test_api_error_redacts_key(self, monkeypatch):
        import requests

        def boom(*a, **kw):
            raise Exception("401 unauthorized key=fake-key-for-testing")

        monkeypatch.setattr(requests, "post", boom)

        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({"prompt": "test"})
        assert result.success is False
        assert "fake-key-for-testing" not in result.error
        assert "[redacted]" in result.error

    def test_no_urls_returns_error(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: FakeResp({"data": [{"b64_json": "xx"}]}),
        )

        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({"prompt": "test"})
        assert result.success is False
        assert "no image URLs" in result.error

    def test_download_failure_returns_error(self, monkeypatch):
        import requests

        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: FakeResp(_api_response(["https://x/img.png"])),
        )

        def boom(url, **kw):
            raise Exception("download failed")

        monkeypatch.setattr(requests, "get", boom)

        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().execute({"prompt": "test"})
        assert result.success is False
        assert "download failed" in result.error


class TestDryRun:

    def test_dry_run_includes_defaults(self):
        from plugins.openmontage.tools.graphics.zhipu_image import ZhipuImage
        result = ZhipuImage().dry_run({"prompt": "test"})
        assert result["tool"] == "zhipu_image"
        assert result["model"] == "cogview-4-250304"
        assert result["quality"] == "standard"
        assert result["size"] == "1024x1024"
