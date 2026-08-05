"""安装包自动更新单元测试."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest

from plugins.mxai.pkg import install_updater as mod

_PKG_BYTES = b"x" * 4096
_PKG_SHA256 = hashlib.sha256(_PKG_BYTES).hexdigest()


@pytest.fixture(autouse=True)
def _reset_download_thread() -> None:
    mod._download_thread = None
    mod._bg_started = False
    # 确保上次测试未残留 IO 锁 / 进程锁
    if mod._download_process_lock_fh is not None:
        mod._release_download_process_lock()
    if not mod._download_io_lock.acquire(blocking=False):
        try:
            mod._download_io_lock.release()
        except RuntimeError:
            pass
    else:
        mod._download_io_lock.release()
    yield
    if mod._download_thread is not None and mod._download_thread.is_alive():
        mod._download_thread.join(timeout=10)
    mod._download_thread = None
    mod._bg_started = False
    if mod._download_process_lock_fh is not None:
        mod._release_download_process_lock()
    if not mod._download_io_lock.acquire(blocking=False):
        try:
            mod._download_io_lock.release()
        except RuntimeError:
            pass
    else:
        mod._download_io_lock.release()


def test_is_gateway_process_detects_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["agent-hub.exe", "-m", "gateway.run"])
    assert mod._is_gateway_process() is True
    monkeypatch.setattr(sys, "argv", ["gateway.run", "--port", "1"])
    assert mod._is_gateway_process() is True
    monkeypatch.setattr(sys, "argv", ["agent-hub.exe"])
    assert mod._is_gateway_process() is False


def test_gateway_skips_background_checker_and_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(mod, "_is_gateway_process", lambda: True)
    started = {"n": 0}

    def _boom(*_a, **_k):
        started["n"] += 1
        raise AssertionError("gateway must not start download thread")

    monkeypatch.setattr(threading, "Thread", _boom)
    mod.start_background_checker()
    assert mod._bg_started is False
    assert started["n"] == 0

    called = {"n": 0}

    def _locked(**_k):
        called["n"] += 1
        raise AssertionError("gateway must not download")

    monkeypatch.setattr(mod, "_download_update_locked", _locked)
    out = mod.download_update(current_version="1.0.0")
    assert called["n"] == 0
    assert "status" in out
    mod._start_download_async(current_version="1.0.0")
    assert mod._download_thread is None


def test_parse_content_range() -> None:
    assert mod._parse_content_range("bytes 100-199/500") == (100, 199)
    assert mod._parse_content_range("bytes 0-0/504930811") == (0, 0)
    assert mod._parse_content_range("bytes 10-20/*") == (10, 20)
    assert mod._parse_content_range("invalid") is None


def test_start_download_async_is_single_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    calls: list[str] = []

    def _fake_download(*, current_version: str = "", _hold_io_lock: bool = False):
        calls.append(current_version or "")
        import time

        time.sleep(0.2)
        return {"status": "ready"}

    monkeypatch.setattr(mod, "download_update", _fake_download)
    mod._start_download_async(current_version="a")
    mod._start_download_async(current_version="b")
    if mod._download_thread is not None:
        mod._download_thread.join(timeout=5)
    assert calls == ["a"]


def test_range_mismatch_falls_back_to_full_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )

    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial_bytes = _PKG_BYTES[:100]
    partial.write_bytes(partial_bytes)

    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": len(partial_bytes),
                "total_bytes": len(_PKG_BYTES),
                "progress": 2,
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Latest:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 200,
                "data": {
                    "id": "pkg-1",
                    "version": "2.0.0",
                    "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
                    "size_bytes": len(_PKG_BYTES),
                    "file_sha256": _PKG_SHA256,
                },
            }

    class _BadRange:
        status_code = 206
        headers = {"content-range": "bytes 0-99/4096", "content-length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield b"should-not-append"

    class _Full:
        status_code = 200
        headers = {"content-length": str(len(_PKG_BYTES))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield _PKG_BYTES

    streams = [_BadRange(), _Full()]

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Latest()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            return streams.pop(0)

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    payload = mod.download_update(current_version="1.0.0")
    assert payload["status"] == "ready"
    assert partial.read_bytes() == _PKG_BYTES


def test_semver_compare() -> None:
    assert mod.semver_compare("1.0.0", "1.1.0") == -1
    assert mod.semver_compare("2.0.0", "1.9.9") == 1
    assert mod.semver_compare("1.2.3", "1.2.3") == 0


def test_public_status_without_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "1.0.0",
                "has_update": False,
            }
        ),
        encoding="utf-8",
    )
    payload = mod.public_status(current_version="1.0.0")
    assert payload["has_update"] is False
    assert payload["current_version"] == "1.0.0"
    assert payload["settings"]["channel"] == "stable"


def test_check_for_update_detects_newer_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 200,
                "data": {
                    "id": "pkg-1",
                    "version": "2.0.0",
                    "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
                    "size_bytes": 4096,
                    "file_sha256": _PKG_SHA256,
                    "release_notes": "修复问题",
                    "force_upgrade": False,
                    "min_os": "Windows 10 64-bit+",
                    "published_at": "2026-07-01T00:00:00Z",
                },
            }

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Resp()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            assert method == "GET"
            return _StreamCtx()

    class _StreamCtx:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield _PKG_BYTES

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    payload = mod.check_for_update(current_version="1.0.0", force=True)
    if mod._download_thread is not None:
        mod._download_thread.join(timeout=10)
        payload = mod.public_status(current_version="1.0.0")
    assert payload["has_update"] is True
    assert payload["latest_version"] == "2.0.0"
    assert payload["status"] == "ready"
    assert payload["progress"] == 100
    assert payload["file_sha256"] == _PKG_SHA256


def test_download_rejects_sha256_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 200,
                "data": {
                    "id": "pkg-1",
                    "version": "2.0.0",
                    "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
                    "size_bytes": len(_PKG_BYTES),
                    "file_sha256": "0" * 64,
                },
            }

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Resp()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            assert method == "GET"
            return _StreamCtx()

    class _StreamCtx:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield _PKG_BYTES

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    payload = mod.check_for_update(current_version="1.0.0", force=True)
    if mod._download_thread is not None:
        mod._download_thread.join(timeout=10)
        payload = mod.public_status(current_version="1.0.0")
    assert payload["status"] == "error"
    assert "SHA256" in (payload["error"] or "")
    assert not (tmp_path / "updates" / "MxAI-2.0.0-setup.exe").exists()


def test_version_change_discards_partial_and_redownloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )

    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial.write_bytes(b"partial")

    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": len(b"partial"),
                "total_bytes": 4096,
                "progress": 1,
                "package_id": "pkg-old",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 200,
                "data": {
                    "id": "pkg-new",
                    "version": "2.0.0",
                    "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
                    "size_bytes": 4096,
                    "file_sha256": _PKG_SHA256,
                },
            }

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Resp()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            return _StreamCtx()

    class _StreamCtx:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield _PKG_BYTES

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    payload = mod.check_for_update(current_version="1.0.0", force=True)
    if mod._download_thread is not None:
        mod._download_thread.join(timeout=10)
        payload = mod.public_status(current_version="1.0.0")

    assert payload["status"] == "ready"
    assert partial.read_bytes() == _PKG_BYTES


def test_download_failure_keeps_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )

    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial.write_bytes(b"partial")

    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": len(b"partial"),
                "total_bytes": 4096,
                "progress": 1,
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "code": 200,
                "data": {
                    "id": "pkg-1",
                    "version": "2.0.0",
                    "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
                    "size_bytes": 4096,
                    "file_sha256": _PKG_SHA256,
                },
            }

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Resp()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    payload = mod.download_update(current_version="1.0.0")
    assert payload["status"] == "idle"
    assert "network down" in (payload["error"] or "")
    assert partial.exists()
    assert partial.read_bytes() == b"partial"
    assert payload["downloaded_bytes"] == len(b"partial")


def test_midstream_fail_then_resume_with_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中途断网保留半成品；再次下载发 Range，拼成完整包并 ready。"""
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    dest = updates_dir / "MxAI-2.0.0-setup.exe"
    first_half = _PKG_BYTES[:100]
    second_half = _PKG_BYTES[100:]

    state_path = tmp_path / "install_update_state.json"
    pkg_meta = {
        "id": "pkg-1",
        "version": "2.0.0",
        "download_url": "https://cdn.example.com/MxAI-2.0.0-setup.exe",
        "size_bytes": len(_PKG_BYTES),
        "file_sha256": _PKG_SHA256,
    }
    state_path.write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": "",
                "downloaded_bytes": 0,
                "total_bytes": len(_PKG_BYTES),
                "progress": 0,
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        base_url = "https://cs.example.com"

    monkeypatch.setattr(mod, "ControlServerClient", lambda: _FakeClient())

    class _Latest:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"code": 200, "data": pkg_meta}

    class _FailStream:
        status_code = 200
        headers = {"content-length": str(len(_PKG_BYTES))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield first_half
            raise RuntimeError("connection reset")

    class _ResumeStream:
        status_code = 206
        headers = {
            "content-range": f"bytes {len(first_half)}-{len(_PKG_BYTES)-1}/{len(_PKG_BYTES)}",
            "content-length": str(len(second_half)),
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=0):
            yield second_half

    streams = [_FailStream(), _ResumeStream()]
    range_headers: list[str | None] = []

    class _Http:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if "install-packages/latest" in url:
                return _Latest()
            raise AssertionError(url)

        def stream(self, method, url, headers=None):
            range_headers.append((headers or {}).get("Range"))
            return streams.pop(0)

    monkeypatch.setattr(mod.httpx, "Client", lambda **kwargs: _Http())

    fail = mod.download_update(current_version="1.0.0")
    assert fail["status"] == "idle"
    assert "connection reset" in (fail["error"] or "")
    assert dest.exists()
    assert dest.read_bytes() == first_half
    assert fail["downloaded_bytes"] == len(first_half)

    # 前端重检 / status 轮询：idle+has_update 应再拉起（此处直接再调 download）
    ok = mod.download_update(current_version="1.0.0")
    assert range_headers[0] is None  # 首次整包
    assert range_headers[1] == f"bytes={len(first_half)}-"  # 续传
    assert ok["status"] == "ready"
    assert ok["progress"] == 100
    assert dest.read_bytes() == _PKG_BYTES


def test_public_status_restarts_after_idle_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """网络失败后 status=idle 且有半成品；GET status 应再次 _start_download_async。"""
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial.write_bytes(b"partial-data")
    (tmp_path / "install_update_state.json").write_text(
        json.dumps(
            {
                "status": "idle",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": len(b"partial-data"),
                "total_bytes": 4096,
                "progress": 1,
                "error": "connection reset",
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    started: list[str] = []
    monkeypatch.setattr(
        mod,
        "_start_download_async",
        lambda *, current_version="": started.append(current_version or ""),
    )
    payload = mod.public_status(current_version="1.0.0")
    assert payload["status"] == "idle"
    assert payload["has_update"] is True
    assert started == ["1.0.0"]
    assert partial.exists()


def test_force_check_does_not_interrupt_active_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial.write_bytes(b"x" * 100)

    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "downloading",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": 100,
                "total_bytes": 4096,
                "progress": 2,
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    class _Alive:
        def is_alive(self):
            return True

        def join(self, timeout=None):
            return None

    mod._download_thread = _Alive()  # type: ignore[assignment]
    try:
        fetch_calls: list[str] = []

        def _no_fetch(**kwargs):
            fetch_calls.append("hit")
            raise AssertionError("force check must not fetch while downloading")

        monkeypatch.setattr(mod, "_fetch_latest_package", _no_fetch)

        payload = mod.check_for_update(current_version="1.0.0", force=True)
        assert payload["status"] == "downloading"
        assert fetch_calls == []
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["status"] == "downloading"
        assert partial.exists()
    finally:
        mod._download_thread = None


def test_finalize_uses_precomputed_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    pkg = updates_dir / "MxAI-2.0.0-setup.exe"
    pkg.write_bytes(_PKG_BYTES)
    state = mod.InstallUpdateState(
        status="downloading",
        latest_version="2.0.0",
        has_update=True,
        local_path=str(pkg),
        downloaded_bytes=len(_PKG_BYTES),
        total_bytes=len(_PKG_BYTES),
        progress=99,
        file_sha256=_PKG_SHA256,
    )
    # 若走文件重算会成功；这里故意传正确 precomputed，并 monkeypatch 文件哈希确保未调用
    called = {"n": 0}

    def _boom(path, expected):
        called["n"] += 1
        raise AssertionError("should use precomputed")

    monkeypatch.setattr(mod, "_sha256_matches", _boom)
    ok = mod._try_finalize_local_package(
        state,
        pkg,
        expected_sha256=_PKG_SHA256,
        expected_total=len(_PKG_BYTES),
        precomputed_sha256=_PKG_SHA256,
    )
    assert ok is True
    assert state.status == "ready"
    assert state.progress == 100
    assert called["n"] == 0


def test_finalize_salvages_oversized_when_precomputed_sha_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """尾部被其它进程多写时：precomputed SHA 正确则 truncate 后 ready."""
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    pkg = updates_dir / "MxAI-2.0.0-setup.exe"
    pkg.write_bytes(_PKG_BYTES + b"DIRTY_TAIL_BYTES!!!!")
    assert pkg.stat().st_size > len(_PKG_BYTES)
    state = mod.InstallUpdateState(
        status="downloading",
        latest_version="2.0.0",
        has_update=True,
        local_path=str(pkg),
        downloaded_bytes=len(_PKG_BYTES),
        total_bytes=len(_PKG_BYTES),
        progress=99,
        file_sha256=_PKG_SHA256,
    )
    ok = mod._try_finalize_local_package(
        state,
        pkg,
        expected_sha256=_PKG_SHA256,
        expected_total=len(_PKG_BYTES),
        precomputed_sha256=_PKG_SHA256,
    )
    assert ok is True
    assert state.status == "ready"
    assert pkg.stat().st_size == len(_PKG_BYTES)
    assert pkg.read_bytes() == _PKG_BYTES


def test_download_skips_when_process_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    monkeypatch.setattr(mod, "_try_acquire_download_process_lock", lambda: False)
    called = {"n": 0}

    def _boom(**kwargs):
        called["n"] += 1
        raise AssertionError("should not enter locked download")

    monkeypatch.setattr(mod, "_download_update_locked", _boom)
    out = mod.download_update(current_version="1.0.0")
    assert called["n"] == 0
    assert "status" in out


def test_oversized_partial_wiped_on_status_poll(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        mod,
        "read_client_settings",
        lambda: {"update": {"channel": "stable"}},
    )
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    partial = updates_dir / "MxAI-2.0.0-setup.exe"
    partial.write_bytes(b"x" * 8192)

    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "downloading",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(partial),
                "downloaded_bytes": 8192,
                "total_bytes": 4096,
                "progress": 99,
                "package_id": "pkg-1",
                "file_sha256": _PKG_SHA256,
                "download_url_key": "/MxAI-2.0.0-setup.exe",
            }
        ),
        encoding="utf-8",
    )

    payload = mod.public_status(current_version="1.0.0")
    assert payload["status"] == "downloading" or payload["status"] == "idle"
    assert not partial.exists()


def test_mark_installing_does_not_persist_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    pkg = updates_dir / "MxAI-2.0.0-setup.exe"
    pkg.write_bytes(_PKG_BYTES)
    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(pkg),
                "downloaded_bytes": len(_PKG_BYTES),
                "total_bytes": len(_PKG_BYTES),
                "progress": 100,
                "file_sha256": _PKG_SHA256,
            }
        ),
        encoding="utf-8",
    )

    payload = mod.mark_installing()
    assert payload["status"] == "ready"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"


def test_load_state_recovers_legacy_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    updates_dir = tmp_path / "updates"
    updates_dir.mkdir(parents=True)
    pkg = updates_dir / "MxAI-2.0.0-setup.exe"
    pkg.write_bytes(_PKG_BYTES)
    state_path = tmp_path / "install_update_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "installing",
                "current_version": "1.0.0",
                "latest_version": "2.0.0",
                "has_update": True,
                "local_path": str(pkg),
                "downloaded_bytes": len(_PKG_BYTES),
                "total_bytes": len(_PKG_BYTES),
                "progress": 100,
                "file_sha256": _PKG_SHA256,
            }
        ),
        encoding="utf-8",
    )

    state = mod._load_state()
    assert state.status == "ready"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
