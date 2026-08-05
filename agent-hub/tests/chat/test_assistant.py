"""个人助手：Hermes assistant Profile + MxAI MCP tools."""

from __future__ import annotations

import json

import pytest

from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture
def hermes_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SERVER_KEY", "test-key")
    monkeypatch.setenv("MXAI_MOCK", "0")


def test_operational_faq_defers_to_hermes(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
    hermes_real,
) -> None:
    from plugins.mxai.agents import assistant as mod

    calls: list[str] = []

    def fake_hermes(message: str, **_kw):
        calls.append(message)
        return {"text": "📊 已生成本周全渠道报表 rpt_test", "source": "assistant_tool"}

    monkeypatch.setattr(mod, "_hermes_session_chat", fake_hermes)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "帮我导出本周 全渠道 表", "agent": "assistant", "stream": False},
    ).json()
    assert calls == ["帮我导出本周 全渠道 表"]
    assert body["reply"]["source"] == "assistant_tool"
    assert "rpt_" in body["reply"]["text"]


def test_assistant_routes_douyin_via_hermes_tools(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
    hermes_real,
) -> None:
    from plugins.mxai.agents import assistant as mod
    from plugins.mxai.mcp_tools import _handle_queue_enqueue

    QueueManager.reset()
    QueueManager.get().arm_work()  # CR-85：未开始工作不可入队，先武装

    def fake_hermes(message: str, **_kw):
        raw = _handle_queue_enqueue(
            {
                "profile_id": "douyin",
                "task_type": "comment_collect",
                "name": "评论意向客户采集",
                "payload": {"keywords": ["咨询"]},
            }
        )
        data = json.loads(raw)
        return {
            "text": f"✅ 已下发：抖音 Agent「评论意向客户采集」任务已入队（{data['task_id']}）。",
            "source": "assistant_tool",
        }

    monkeypatch.setattr(mod, "_hermes_session_chat", fake_hermes)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "启动抖音评论抓取", "agent": "assistant"},
    ).json()
    assert body["reply"]["source"] == "assistant_tool"
    assert "抖音" in body["reply"]["text"]
    q = QueueManager.get()
    assert any(t.profile_id == "douyin" and t.task_type == "comment_collect" for t in q._tasks.values())


def test_assistant_fuzzy_report(mxai_client, hermes_real, monkeypatch: pytest.MonkeyPatch) -> None:
    from plugins.mxai.agents import assistant as mod

    monkeypatch.setattr(
        mod,
        "_hermes_session_chat",
        lambda _m, **_k: {"text": "📊 已生成本周报表 rpt_x", "source": "assistant_tool"},
    )
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "生成报表", "agent": "assistant"},
    ).json()
    assert body["reply"]["source"] == "assistant_tool"


def test_assistant_unknown_agent(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "hello", "agent": "not_a_profile"},
    )
    assert resp.status_code == 404


def test_assistant_generic_not_marketing_mock(mxai_client) -> None:
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "文章 5000字", "agent": "assistant", "stream": False},
    ).json()
    text = body["reply"]["text"]
    assert "营销顾问" not in text
    assert "感谢您的咨询" not in text
    # CR-125：知识库不再直接回复，助理 source 恒为 assistant_*（KB 改注入 profile agent）。
    assert body["reply"]["source"].startswith("assistant")


def test_assistant_kb_not_direct_reply(mxai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-125 · FR-KB-20 回归：助理命中知识库**不再直答**「根据知识库：…」.

    命中切片改由 ``_kb_inject_context`` 取 top-X 注入 profile agent 链路（RAG），
    由大模型据此用自己的话作答；source 恒为 assistant_*（绝不为 "kb"）。
    """
    from plugins.mxai.agents import assistant as mod

    monkeypatch.setattr(
        mod,
        "kb_search_chunks",
        lambda *a, **k: [{"text": "公司退货政策：7 天无理由退换。", "score": 0.9}],
    )
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "退货政策是什么", "agent": "assistant", "stream": False},
    ).json()
    assert "根据知识库" not in body["reply"]["text"]
    assert body["reply"]["source"] != "kb"
    assert body["reply"]["source"].startswith("assistant")
    # 注入 helper：命中切片正文进入 kb_context（供 LLM 参考、非直接回复）。
    assert "退货政策" in mod._kb_inject_context("退货政策是什么")


def test_assistant_unavailable_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
) -> None:
    """无 API_SERVER_KEY 时兜底文案**准确**提示配 key（而非笼统「连不上」）。"""
    from plugins.mxai.agents import assistant as mod

    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    monkeypatch.setenv("MXAI_MOCK", "0")

    monkeypatch.setattr(mod, "_hermes_session_chat", lambda _m, **_k: None)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "文章 5000字", "agent": "assistant", "stream": False},
    ).json()
    assert body["reply"]["source"] == "assistant_llm_fallback"
    # key 确实缺失 → 文案准确指向 API_SERVER_KEY（不臆断 api_server 未启动等）。
    assert "API_SERVER_KEY" in body["reply"]["text"]


def test_assistant_unavailable_with_key_is_neutral(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
) -> None:
    """key 已配但仍无回复 → 兜底文案**不**误甩 API_SERVER_KEY，给中性指引（指向日志）。"""
    from plugins.mxai.agents import assistant as mod

    monkeypatch.setenv("API_SERVER_KEY", "test-key")
    monkeypatch.setenv("MXAI_MOCK", "0")

    monkeypatch.setattr(mod, "_hermes_session_chat", lambda _m, **_k: None)
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "文章 5000字", "agent": "assistant", "stream": False},
    ).json()
    assert body["reply"]["source"] == "assistant_llm_fallback"
    text = body["reply"]["text"]
    assert "API_SERVER_KEY" not in text  # 不误导
    assert "日志" in text or "模型" in text  # 中性、可排查


def test_assistant_surfaces_gateway_auth_detail(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
) -> None:
    """网关/官方渠道鉴权失败 → 透传 detail，不做客户端预拦截。"""
    from plugins.mxai.agents import assistant as mod

    monkeypatch.setenv("API_SERVER_KEY", "test-key")
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setattr(
        mod,
        "_hermes_session_chat",
        lambda _m, **_k: {
            "text": "",
            "detail": "官方渠道需要登录：未检测到设备会话（JWT）。请重新登录后重试。",
        },
    )

    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "你好", "agent": "assistant", "stream": False},
    ).json()
    assert body["reply"]["source"] == "assistant_llm_fallback"
    assert "JWT" in body["reply"]["text"] or "登录" in body["reply"]["text"]
    assert "未设 model" not in body["reply"]["text"]


def test_assistant_stream(
    monkeypatch: pytest.MonkeyPatch,
    mxai_client,
    hermes_real,
) -> None:
    def fake_events(*_args, **_kwargs):
        yield {"event": "delta", "delta": "✅ "}
        yield {"event": "delta", "delta": "已下发抖音任务"}
        yield {
            "event": "completed",
            "content": "✅ 已下发抖音任务",
            "usage": {"tool_call_count": 1},
        }

    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.iter_profile_agent_events",
        fake_events,
    )
    with mxai_client.stream(
        "POST",
        "/api/plugins/mxai/chat/completions",
        json={"message": "启动抖音评论抓取", "agent": "assistant", "stream": True},
    ) as resp:
        assert resp.status_code == 200
        frames = []
        for line in resp.iter_lines():
            if line and line.startswith("data:"):
                frames.append(json.loads(line[5:]))
        deltas = [
            f
            for f in frames
            if f.get("data", {}).get("delta") and not f.get("data", {}).get("done")
        ]
        assert len(deltas) >= 2
        done = [f for f in frames if f.get("data", {}).get("done")]
        assert done
        assert done[-1]["data"]["reply"]["source"] == "assistant_tool"
        assert done[-1]["data"]["reply"]["text"] == "✅ 已下发抖音任务"
