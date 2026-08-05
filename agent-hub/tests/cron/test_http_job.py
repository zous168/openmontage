"""Hermes cron HTTP 执行类型（CR-132 方案 A）：create_job(http=...) + run_job http 分支."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_create_job_stores_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job

    job = create_job(
        prompt="x",
        schedule="every 30m",
        id="mxai-test-http",
        http={"url": "http://127.0.0.1:8642/api/plugins/mxai/cron/run/maintenance/default", "method": "POST"},
    )
    assert job["http"]["url"].endswith("/cron/run/maintenance/default")
    assert job["http"]["method"] == "POST"
    assert job.get("script") is None
    assert job.get("no_agent") is False


def test_create_job_http_requires_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job

    with pytest.raises(ValueError):
        create_job(prompt="x", schedule="every 30m", http={"method": "POST"})  # 无 url


def test_update_job_sets_and_normalizes_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job, update_job

    job = create_job(prompt="x", schedule="every 30m", id="mxai-test-switch")
    updated = update_job(
        job["id"],
        {"http": {"url": "http://127.0.0.1:8642/api/x", "method": "post", "timeout": 30}, "script": None},
    )
    assert updated is not None
    assert updated["http"]["url"] == "http://127.0.0.1:8642/api/x"
    assert updated["http"]["method"] == "POST"  # 归一化大写
    assert updated["http"]["timeout"] == 30.0


def test_update_job_clears_http_on_mode_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job, update_job

    job = create_job(prompt="x", schedule="every 30m", id="mxai-test-clear", http={"url": "http://x"})
    assert job["http"]["url"] == "http://x"
    updated = update_job(job["id"], {"http": None, "prompt": "hello", "no_agent": False})
    assert updated is not None
    assert updated.get("http") is None  # 切回 agent 模式清空 http


def test_update_job_http_requires_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job, update_job

    job = create_job(prompt="x", schedule="every 30m", id="mxai-test-badurl")
    with pytest.raises(ValueError):
        update_job(job["id"], {"http": {"method": "POST"}})  # 无 url


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_run_http_job_2xx_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setattr("httpx.request", lambda *a, **k: _Resp(200, '{"ok": true, "enqueued": 2}'))
    ok, output, final, err = sched._run_http_job(
        {"id": "j1", "name": "触达"}, {"url": "http://x", "method": "POST"}
    )
    assert ok is True
    assert err is None
    assert "enqueued" in output  # 回执入 output（Hermes save_job_output）
    assert final  # 非空，避免 _process_job 误判 empty


def test_run_http_job_non_2xx_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setattr("httpx.request", lambda *a, **k: _Resp(500, "boom"))
    ok, _output, _final, err = sched._run_http_job({"id": "j1", "name": "n"}, {"url": "http://x"})
    assert ok is False
    assert "500" in (err or "")


def test_run_http_job_exception_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    def _boom(*a, **k):
        raise RuntimeError("conn refused")

    monkeypatch.setattr("httpx.request", _boom)
    ok, _output, _final, err = sched._run_http_job({"id": "j1", "name": "n"}, {"url": "http://x"})
    assert ok is False
    assert "conn refused" in (err or "")


def test_run_http_job_passes_dynamic_callback_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """执行器执行时**动态构造**并**传递** callback URL（X-Cron-Callback 头）：
    ``{业务url的base}/api/cron/jobs/{job_id}/callback``，不入配置。"""
    from cron import scheduler as sched

    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured["headers"] = kwargs.get("headers")
        return _Resp(200, "ok")

    monkeypatch.setattr("httpx.request", _fake)
    sched._run_http_job(
        {"id": "mxai-wechat-scheduled_touch", "name": "n"},
        {"url": "http://127.0.0.1:8642/api/plugins/mxai/cron/run/scheduled_touch/wechat"},
    )
    assert (
        captured["headers"].get("X-Cron-Callback")
        == "http://127.0.0.1:8642/api/cron/jobs/mxai-wechat-scheduled_touch/callback"
    )
    # 每次执行唯一 run_id 也随请求下发（执行端回调时带上，供按执行对账）
    run_id = captured["headers"].get("X-Cron-Run-Id")
    assert run_id and len(run_id) >= 8


def test_append_job_output_for_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """异步回调把「Callback 返回」段追加到那次执行（按 run_id）的**同一条**记录。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import append_job_output_for_run, save_job_output

    save_job_output("mxai-test", "# Cron Job\n**Run ID:** RID123\n\n## 同步返回\n\nsync-result\n")
    assert append_job_output_for_run("mxai-test", "RID123", "\n## Callback 返回\ncb-result\n") is True
    assert append_job_output_for_run("mxai-test", "NOPE", "x") is False  # 未知 run_id

    out_dir = tmp_path / "cron" / "output" / "mxai-test"
    content = next(out_dir.glob("*.md")).read_text(encoding="utf-8")
    # 一条记录里：同步返回 在前，Callback 返回 在后（顺序正确）
    assert content.index("sync-result") < content.index("cb-result")


def test_expand_cron_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron.scheduler import _expand_cron_placeholders

    monkeypatch.setenv("API_SERVER_KEY", "sekret")
    job = {"id": "mxai-wechat-scheduled_touch", "name": "微信·存量定时触达"}
    assert _expand_cron_placeholders("Bearer {env.API_SERVER_KEY}", job) == "Bearer sekret"
    assert _expand_cron_placeholders("id={cronId}", job) == "id=mxai-wechat-scheduled_touch"
    assert _expand_cron_placeholders("{cronName}", job) == "微信·存量定时触达"
    # 未知占位符原样保留（避免误伤 body 里的 {..} 字面量）
    assert _expand_cron_placeholders("{unknown} {a.b}", job) == "{unknown} {a.b}"
    # 递归 dict/list
    out = _expand_cron_placeholders(
        {"Authorization": "Bearer {env.API_SERVER_KEY}", "x": ["{cronId}"]}, job
    )
    assert out == {"Authorization": "Bearer sekret", "x": ["mxai-wechat-scheduled_touch"]}


def test_expand_local_ipc_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """{ipc_token} 执行时展开为本机 IPC token（MxAI 标准鉴权），不落 jobs.json。"""
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.scheduler import _expand_cron_placeholders
    from core.platform.device.local_ipc import get_or_create_ipc_token

    expected = get_or_create_ipc_token()
    out = _expand_cron_placeholders({"X-Hub-Local-Token": "{ipc_token}"}, {"id": "j1"})
    assert out["X-Hub-Local-Token"] == expected


def test_run_http_job_sends_string_body_as_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """字符串 body 按真实请求原样发（content），dict body 走 json——占位符先展开。"""
    from cron import scheduler as sched

    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return _Resp(200, "ok")

    monkeypatch.setattr("httpx.request", _fake)
    sched._run_http_job(
        {"id": "j1", "name": "n"},
        {"url": "http://x", "method": "POST", "body": '{"uid": "{cronId}"}'},
    )
    assert captured.get("content") == b'{"uid": "j1"}'  # 字符串 body 原样 + 占位符展开
    assert "json" not in captured


def test_run_http_job_sends_dict_body_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return _Resp(200, "ok")

    monkeypatch.setattr("httpx.request", _fake)
    sched._run_http_job({"id": "j1", "name": "n"}, {"url": "http://x", "body": {"a": 1}})
    assert captured.get("json") == {"a": 1}
    assert "content" not in captured


def test_run_http_job_expands_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setenv("API_SERVER_KEY", "sekret")
    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _Resp(200, '{"ok": true}')

    monkeypatch.setattr("httpx.request", _fake)
    ok, _doc, _final, err = sched._run_http_job(
        {"id": "j1", "name": "n"},
        {
            "url": "http://x/{cronId}",
            "method": "POST",
            "headers": {"Authorization": "Bearer {env.API_SERVER_KEY}"},
        },
    )
    assert ok is True and err is None
    assert captured["url"] == "http://x/j1"  # url 占位符展开
    assert captured["headers"]["Authorization"] == "Bearer sekret"  # 密钥执行时才注入


def test_run_http_job_loopback_disables_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """127.0.0.1 loopback 须 trust_env=False，避免 Windows 系统代理导致 502。"""
    from cron import scheduler as sched

    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured["trust_env"] = kwargs.get("trust_env")
        return _Resp(200, "ok")

    monkeypatch.setattr("httpx.request", _fake)
    sched._run_http_job(
        {"id": "j1", "name": "n"},
        {"url": "http://127.0.0.1:8642/api/plugins/mxai/cron/run/boss_greet_schedule/boss"},
    )
    assert captured["trust_env"] is False


def test_run_http_job_external_url_keeps_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    captured: dict = {}

    def _fake(method, url, **kwargs):  # noqa: ANN001
        captured["trust_env"] = kwargs.get("trust_env")
        return _Resp(200, "ok")

    monkeypatch.setattr("httpx.request", _fake)
    sched._run_http_job({"id": "j1", "name": "n"}, {"url": "https://example.com/hook"})
    assert captured["trust_env"] is True
