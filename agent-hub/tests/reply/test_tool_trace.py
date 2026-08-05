"""CR-120 LT-034.04.1：工具/技能调用过程内联 tool_trace 捕获.

调试 LLM 应答触发 Agent 工具/技能调用时，把每步调用抽成 ``tool_trace`` 随回复返回
（供前端内联进对话）：``[{seq,type,name,input,output,duration_ms,ok}]``（type∈tool|skill|mcp）。
仅加遥测，不改 FAQ/KB/LLM 应答选择逻辑。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.mxai.agents import hermes_agent
from plugins.mxai.agents.pipeline import resolve_reply


# ─── 1. SSE 工具事件解析 → tool_trace（含 run.completed 权威 transcript） ───


def _sse_lines_with_tool_run() -> list[str]:
    """带工具事件 + run.completed transcript（含 tool 输出）的 Hermes SSE 流帧。"""
    transcript = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "kb_search",
                            "arguments": json.dumps({"query": "本地部署"}, ensure_ascii=False),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "命中 3 条切片…"},
        ],
        "usage": {"tool_call_count": 1, "input_tokens": 10, "output_tokens": 5},
        "model": "deepseek-chat",
    }
    return [
        "event: tool.started",
        'data: {"tool_name":"kb_search","args":{"query":"本地部署"}}',
        "",
        "event: tool.completed",
        'data: {"tool_name":"kb_search"}',
        "",
        "event: assistant.delta",
        'data: {"delta":"已为您查询。"}',
        "",
        "event: assistant.completed",
        'data: {"content":"已为您查询。","usage":{"tool_call_count":1}}',
        "",
        "event: run.completed",
        f"data: {json.dumps(transcript, ensure_ascii=False)}",
        "",
    ]


def test_iter_parsed_sse_surfaces_tool_and_run_messages() -> None:
    events = list(hermes_agent._iter_parsed_sse_events(iter(_sse_lines_with_tool_run())))
    kinds = [e["event"] for e in events]
    assert "tool.started" in kinds
    assert "tool.completed" in kinds
    started = next(e for e in events if e["event"] == "tool.started")
    assert started["tool_name"] == "kb_search"
    assert started["args"] == {"query": "本地部署"}
    run = next(e for e in events if e["event"] == "run_completed")
    assert run["messages"][0]["role"] == "assistant"
    assert run["messages"][1]["content"] == "命中 3 条切片…"


def test_tool_trace_from_messages_has_input_output() -> None:
    transcript = json.loads(
        next(
            ln[len("data: "):]
            for ln in _sse_lines_with_tool_run()
            if ln.startswith("data: {") and '"messages"' in ln
        )
    )
    trace = hermes_agent._tool_trace_from_messages(transcript["messages"])
    assert len(trace) == 1
    step = trace[0]
    assert step["seq"] == 1
    assert step["type"] == "tool"
    assert step["name"] == "kb_search"
    assert step["input"] == json.dumps({"query": "本地部署"}, ensure_ascii=False)
    assert step["output"] == "命中 3 条切片…"
    assert step["ok"] is True
    # duration_ms 此源不可得 → None（不臆造）
    assert step["duration_ms"] is None


def test_complete_profile_agent_reply_attaches_tool_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hermes_agent,
        "iter_profile_agent_events",
        lambda *a, **k: hermes_agent._iter_parsed_sse_events(iter(_sse_lines_with_tool_run())),
    )
    result = hermes_agent.complete_profile_agent_reply("douyin", "支持本地部署吗")
    assert result is not None
    assert result["text"] == "已为您查询。"
    trace = result["tool_trace"]
    assert len(trace) == 1
    assert trace[0]["name"] == "kb_search"
    assert trace[0]["output"] == "命中 3 条切片…"


def test_tool_trace_empty_when_no_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        "event: assistant.delta",
        'data: {"delta":"你好"}',
        "",
        "event: assistant.completed",
        'data: {"content":"你好","usage":{}}',
        "",
        "event: run.completed",
        'data: {"usage":{},"messages":[]}',
        "",
    ]
    monkeypatch.setattr(
        hermes_agent,
        "iter_profile_agent_events",
        lambda *a, **k: hermes_agent._iter_parsed_sse_events(iter(lines)),
    )
    result = hermes_agent.complete_profile_agent_reply("douyin", "你好")
    assert result is not None
    assert result["tool_trace"] == []


# ─── 2. 流内事件兜底（run.completed 无 transcript） + 类型分类 + 截断 ───


def test_tool_trace_event_fallback_and_failed_marks_ok_false() -> None:
    events = [
        {"event": "tool.started", "tool_name": "mcp__weather__lookup", "args": {"city": "深圳"}},
        {"event": "tool.failed", "tool_name": "mcp__weather__lookup"},
        {"event": "tool.started", "tool_name": "run_skill", "args": {"name": "greet"}},
        {"event": "tool.completed", "tool_name": "run_skill"},
    ]
    trace = hermes_agent._build_tool_trace(events, [])
    assert len(trace) == 2
    assert trace[0]["type"] == "mcp"
    assert trace[0]["ok"] is False  # tool.failed 标记失败
    assert trace[0]["output"] is None  # 流内事件无 output（照实 None）
    assert trace[1]["type"] == "skill"
    assert trace[1]["ok"] is True


# ─── 2b. LT-034.04.1b：tool.completed/failed 携带 duration/is_error → 真实 duration_ms/ok ───


def test_duration_to_ms_conversion() -> None:
    assert hermes_agent._duration_to_ms(1.234) == 1234
    assert hermes_agent._duration_to_ms(0.0007) == 1  # round → 1ms
    assert hermes_agent._duration_to_ms(0) == 0
    # 缺字段 / 非数 / 负值 → None（旧 server 兼容，不臆造）
    assert hermes_agent._duration_to_ms(None) is None
    assert hermes_agent._duration_to_ms("nope") is None
    assert hermes_agent._duration_to_ms(-1.0) is None


def test_event_fallback_real_duration_ms_and_ok() -> None:
    """流内 tool.completed/failed 携带 duration（秒）/is_error → 真实 duration_ms、ok。"""
    events = [
        {"event": "tool.started", "tool_name": "kb_search", "args": {"q": "x"}},
        {"event": "tool.completed", "tool_name": "kb_search", "duration": 0.512, "is_error": False},
        {"event": "tool.started", "tool_name": "http_call", "args": {"url": "y"}},
        # agent core 仅发 tool.completed，失败时携带 is_error=True
        {"event": "tool.completed", "tool_name": "http_call", "duration": 1.25, "is_error": True},
    ]
    trace = hermes_agent._build_tool_trace(events, [])
    assert trace[0]["duration_ms"] == 512
    assert trace[0]["ok"] is True
    assert trace[1]["duration_ms"] == 1250
    assert trace[1]["ok"] is False  # is_error=True → ok False


def test_event_fallback_missing_duration_stays_null() -> None:
    """旧 server / 缺 duration 字段 → duration_ms 优雅置 None（向后兼容），ok 仍按事件名。"""
    events = [
        {"event": "tool.started", "tool_name": "kb_search", "args": {"q": "x"}},
        {"event": "tool.completed", "tool_name": "kb_search"},  # 无 duration/is_error
        {"event": "tool.started", "tool_name": "bad", "args": {}},
        {"event": "tool.failed", "tool_name": "bad"},  # 旧式 failed 事件、无字段
    ]
    trace = hermes_agent._build_tool_trace(events, [])
    assert trace[0]["duration_ms"] is None
    assert trace[0]["ok"] is True
    assert trace[1]["duration_ms"] is None
    assert trace[1]["ok"] is False  # tool.failed → ok False


def test_transcript_backfilled_with_real_duration_from_events() -> None:
    """权威 transcript（含 output）+ 流内 completed/failed → 回填真实 duration_ms/ok。"""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "function": {"name": "kb_search", "arguments": "{}"}},
                {"id": "c2", "function": {"name": "http_call", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "命中"},
        {"role": "tool", "tool_call_id": "c2", "content": "500"},
    ]
    events = [
        {"event": "tool.started", "tool_name": "kb_search"},
        {"event": "tool.completed", "tool_name": "kb_search", "duration": 0.2, "is_error": False},
        {"event": "tool.started", "tool_name": "http_call"},
        {"event": "tool.completed", "tool_name": "http_call", "duration": 2.0, "is_error": True},
    ]
    trace = hermes_agent._build_tool_trace(events, messages)
    assert trace[0]["output"] == "命中"  # transcript output 保留
    assert trace[0]["duration_ms"] == 200
    assert trace[0]["ok"] is True
    assert trace[1]["duration_ms"] == 2000
    assert trace[1]["ok"] is False  # is_error 回填失败态


def test_iter_parsed_sse_surfaces_duration_and_is_error() -> None:
    """SSE 解析把 tool.completed 的 duration/is_error 透出到事件 dict（供 trace 填充）。"""
    lines = [
        "event: tool.started",
        'data: {"tool_name":"kb_search","args":{}}',
        "",
        "event: tool.completed",
        'data: {"tool_name":"kb_search","duration":0.333,"is_error":false}',
        "",
    ]
    events = list(hermes_agent._iter_parsed_sse_events(iter(lines)))
    completed = next(e for e in events if e["event"] == "tool.completed")
    assert completed["duration"] == 0.333
    assert completed["is_error"] is False


def test_tool_trace_field_truncation() -> None:
    long = "x" * 700
    out = hermes_agent._truncate_trace_field(long)
    assert out.endswith("…[truncated]")
    assert len(out) == hermes_agent._TOOL_TRACE_FIELD_MAX + len("…[truncated]")
    assert hermes_agent._truncate_trace_field(None) is None


def test_is_debug_hermes_session() -> None:
    assert hermes_agent._is_debug_hermes_session("mxai-wechat-debug-abcd", None)
    assert hermes_agent._is_debug_hermes_session(None, "agent:wechat:debug:abcd")
    assert not hermes_agent._is_debug_hermes_session(
        "mxai-wechat-inbound-abcd", "agent:wechat:inbound:abcd"
    )


def test_approval_sse_parses_and_debug_auto_approve_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approval.request → event=approval；调试会话路径须调用 once 放行。"""
    lines = [
        "event: approval.request",
        'data: {"command":"ls","description":"list"}',
        "",
    ]
    events = list(hermes_agent._iter_parsed_sse_events(iter(lines)))
    assert events == [
        {
            "event": "approval",
            "command": "ls",
            "description": "list",
            "choices": ["once", "session", "always", "deny"],
            "allow_permanent": True,
        }
    ]

    calls: list[tuple] = []
    monkeypatch.setattr(
        hermes_agent,
        "resolve_session_chat_approval",
        lambda pid, sid, skey, choice: calls.append((pid, sid, skey, choice))
        or {"ok": True},
    )
    sid = "mxai-qiyeweixin_chat-debug-deadbeef"
    skey = "agent:qiyeweixin_chat:debug:deadbeef"
    for item in events:
        if item.get("event") == "approval" and hermes_agent._is_debug_hermes_session(
            sid, skey
        ):
            hermes_agent.resolve_session_chat_approval(
                "qiyeweixin_chat", sid, skey, "once"
            )
    assert calls == [("qiyeweixin_chat", sid, skey, "once")]


def test_build_llm_io_from_transcript_and_synthetic() -> None:
    io = hermes_agent.build_llm_io(
        [
            {"role": "system", "content": "你是客服"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "function": {"name": "kb_search", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "hit"},
            {"role": "user", "content": "本地部署？"},
        ],
        "支持本地部署",
    )
    assert io["response"] == "支持本地部署"
    assert [m["role"] for m in io["messages"]] == ["system", "assistant", "tool", "user"]
    assert io["messages"][1]["tool_calls"] == ["kb_search"]
    assert io["messages"][2]["tool_call_id"] == "c1"

    syn = hermes_agent.build_llm_io(
        None, "stub", user_message="你好", kb_context="切片A", profile_id="wechat_chat"
    )
    assert syn["messages"] == [{"role": "user", "content": "你好"}]
    assert syn["response"] == "stub"
    assert syn["request_source"] == "unavailable"
    assert "llm_api_requests" in syn["warning"]

    long = "y" * (hermes_agent._LLM_IO_FIELD_MAX + 50)
    cut = hermes_agent.build_llm_io(None, long, user_message=long)
    assert cut["response"].endswith("…[truncated]")
    assert cut["messages"][0]["content"].endswith("…[truncated]")


def test_build_llm_io_drops_duplicate_assistant_and_adds_user() -> None:
    """run.completed 仅含 assistant 时，请求区不应与 response 重复，且补 user（不伪造 system）。"""
    io = hermes_agent.build_llm_io(
        [{"role": "assistant", "content": "你好！有什么可以帮你吗？"}],
        "你好！有什么可以帮你吗？",
        user_message="你好",
        profile_id="qiyeweixin_chat",
        session_id="mxai-qiyeweixin_chat-debug-abc",
    )
    assert io["response"] == "你好！有什么可以帮你吗？"
    assert io["messages"] == [{"role": "user", "content": "你好"}]
    assert io["request_source"] == "transcript_only"
    assert "llm_api_requests" in io["warning"]
    assert not any(m.get("role") == "system" for m in io["messages"])


def test_messages_from_llm_request_json_includes_system() -> None:
    raw = json.dumps(
        {
            "model": "test",
            "system": "你是企业微信客服",
            "messages": [{"role": "user", "content": "你好"}],
        },
        ensure_ascii=False,
    )
    msgs = hermes_agent._messages_from_llm_request_json(raw)
    assert msgs[0]["role"] == "system"
    assert "企业微信" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"


def test_tools_from_llm_payload_openai_shape() -> None:
    payload = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Find files",
                },
            }
        ]
    }
    tools = hermes_agent._tools_from_llm_payload(payload)
    assert tools == [{"name": "search_files", "description": "Find files"}]


def test_skills_from_system_text_parses_available_skills() -> None:
    text = (
        "## Skills\n"
        "<available_skills>\n"
        "  coding:\n"
        "    - hermes-agent: Configure Hermes\n"
        "    - github-operations: GitHub workflow\n"
        "</available_skills>\n"
    )
    skills = hermes_agent._skills_from_system_text(text)
    assert skills == ["hermes-agent", "github-operations"]


def test_skills_used_from_tool_trace_skill_view_only() -> None:
    trace = [
        {
            "seq": 1,
            "type": "skill",
            "name": "skill_view",
            "input": {"name": "sales-talk"},
        },
        {
            "seq": 2,
            "type": "tool",
            "name": "mxai_kb_search",
            "input": {"query": "x"},
        },
        {
            "seq": 3,
            "type": "skill",
            "name": "skill_view",
            "input": '{"name":"sales-talk"}',
        },
    ]
    assert hermes_agent._skills_used_from_tool_trace(trace) == ["sales-talk"]


def test_skills_used_from_tool_trace_falls_back_to_output_name() -> None:
    """input 被冲掉时，仍可从 skill_view 返回体解析已加载名。"""
    trace = [
        {
            "seq": 1,
            "type": "skill",
            "name": "skill_view",
            "input": None,
            "output": '{"success": true, "name": "sales-talk", "content": "..."}',
        }
    ]
    assert hermes_agent._skills_used_from_tool_trace(trace) == ["sales-talk"]


def test_build_llm_io_includes_tools_and_skills_from_log(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps(
        {
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "execute_code", "description": "Run code"},
                }
            ],
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        hermes_agent,
        "_fetch_latest_llm_request",
        lambda pid, sid: {
            "messages": hermes_agent._messages_from_llm_request_json(raw),
            "tools": hermes_agent._tools_from_llm_payload(
                hermes_agent._load_llm_request_payload(raw)
            ),
            "skills_available": [],
            "from_log": True,
        },
    )
    io = hermes_agent.build_llm_io(
        None,
        "ok",
        user_message="hi",
        profile_id="assistant",
        session_id="mxai-assistant-debug-abc",
    )
    assert io["tools"][0]["name"] == "execute_code"
    assert io["response"] == "ok"


def test_build_llm_io_prefers_llm_request_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hermes_agent,
        "_fetch_latest_llm_request",
        lambda pid, sid: {
            "messages": [
                {"role": "system", "content": "logged system"},
                {"role": "user", "content": "你好"},
            ],
            "tools": [{"name": "memory"}],
            "skills_available": ["hermes-agent"],
            "from_log": True,
        },
    )
    io = hermes_agent.build_llm_io(
        [{"role": "assistant", "content": "ignored"}],
        "回复",
        user_message="你好",
        profile_id="wechat_chat",
        session_id="mxai-wechat_chat-debug-abc",
    )
    assert io["messages"][0]["content"] == "logged system"
    assert io["tools"][0]["name"] == "memory"
    assert io["skills_available"] == ["hermes-agent"]
    assert io["response"] == "回复"
    assert io["request_source"] == "llm_api_log"


def test_fetch_latest_llm_request_prefers_full_system_over_tool_followup() -> None:
    """Tool 循环末次 API 调用常缺 system/skills，应回溯到含 available_skills 的那条。"""
    followup = json.dumps(
        {
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}, {"role": "tool", "content": "x"}],
            "tools": [{"type": "function", "function": {"name": "kb_search"}}],
        },
        ensure_ascii=False,
    )
    full = json.dumps(
        {
            "model": "test",
            "system": (
                "## Skills\n<available_skills>\n  - sales-talk: Sales\n</available_skills>"
            ),
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "kb_search"}}],
        },
        ensure_ascii=False,
    )

    class _FakeDb:
        def list_llm_api_requests(self, sid, *, limit, offset, include_bodies):
            assert sid == "mxai-wechat_chat-debug-abc"
            return [
                {"request_json": followup},
                {"request_json": full},
            ]

        def close(self):
            return None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hermes_agent, "_profile_session_db", lambda pid: _FakeDb())
    try:
        bundle = hermes_agent._fetch_latest_llm_request(
            "wechat_chat", "mxai-wechat_chat-debug-abc"
        )
    finally:
        monkey.undo()

    assert bundle is not None
    assert bundle["messages"][0]["role"] == "system"
    assert "available_skills" in bundle["messages"][0]["content"]
    assert "sales-talk" in bundle["skills_available"]


def test_fetch_latest_llm_request_prefers_longer_history_when_skills_tie() -> None:
    """同含 skills 时选消息更多的请求，避免诊断 prompt 丢掉多轮历史。"""
    short = json.dumps(
        {
            "model": "test",
            "messages": [
                {
                    "role": "system",
                    "content": "<available_skills>\n  - sales-talk: S\n</available_skills>",
                },
                {"role": "user", "content": "你好"},
            ],
            "tools": [{"name": "skill_view"}],
        },
        ensure_ascii=False,
    )
    long = json.dumps(
        {
            "model": "test",
            "messages": [
                {
                    "role": "system",
                    "content": "<available_skills>\n  - sales-talk: S\n</available_skills>",
                },
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "您好"},
                {"role": "user", "content": "不错"},
            ],
            "tools": [{"name": "skill_view"}],
        },
        ensure_ascii=False,
    )

    class _FakeDb:
        def list_llm_api_requests(self, sid, *, limit, offset, include_bodies):
            # 旧短请求在前（模拟同分时若误选会丢历史）
            return [{"request_json": short}, {"request_json": long}]

        def close(self):
            return None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(hermes_agent, "_profile_session_db", lambda pid: _FakeDb())
    try:
        bundle = hermes_agent._fetch_latest_llm_request(
            "wechat_chat", "mxai-wechat_chat-debug-abc"
        )
    finally:
        monkey.undo()

    assert bundle is not None
    assert len(bundle["messages"]) == 4
    assert bundle["messages"][-1]["content"] == "不错"


def test_build_llm_io_keeps_tool_turn_before_final_response() -> None:
    io = hermes_agent.build_llm_io(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "function": {"name": "kb_search", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "hit"},
            {"role": "assistant", "content": "支持本地部署"},
        ],
        "支持本地部署",
        user_message="能本地部署吗",
    )
    assert io["response"] == "支持本地部署"
    assert [m["role"] for m in io["messages"]] == ["user", "assistant", "tool"]
    assert io["messages"][0]["content"] == "能本地部署吗"
    assert io["messages"][1]["tool_calls"] == ["kb_search"]


# ─── 3. resolve_reply(debug=True) 顶层附 tool_trace ───

_SIX_CHANNELS = ("douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss")


@pytest.fixture
def debug_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for name in _SIX_CHANNELS:
        p = profiles / name
        p.mkdir()
        (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
        (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    get_dir = lambda name: profiles / name  # noqa: E731
    monkeypatch.setattr("plugins.mxai.agents.pipeline.get_profile_dir", get_dir)
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", get_dir)
    return profiles


def test_resolve_reply_debug_attaches_tool_trace_from_llm(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 结果带 tool_trace → resolve_reply(debug=True) 顶层透传真实 trace。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: []
    )
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.complete_profile_agent_reply",
        lambda pid, msg, *, recipient="", allow_fallback=False, **_: {
            "source": "agent_tool",
            "text": "已为您处理。",
            "tool_trace": [
                {
                    "seq": 1,
                    "type": "tool",
                    "name": "kb_search",
                    "input": {"query": "本地部署"},
                    "output": "命中 3 条切片…",
                    "duration_ms": None,
                    "ok": True,
                }
            ],
        },
    )
    result = resolve_reply("douyin", "支持本地部署吗", debug=True, debug_token="tok-tt")
    assert result["tool_trace"][0]["seq"] == 1
    assert result["tool_trace"][0]["name"] == "kb_search"
    assert result["tool_trace"][0]["output"] == "命中 3 条切片…"


def test_resolve_reply_debug_tool_trace_empty_without_tools(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无工具调用（mock LLM 兜底）→ tool_trace == []。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: []
    )
    result = resolve_reply("douyin", "随便聊聊", debug=True, debug_token="tok-empty")
    assert result["source"] == "llm"
    assert result["tool_trace"] == []


def test_resolve_reply_faq_branch_tool_trace_empty(debug_env: Path) -> None:
    """FAQ 命中分支不经 Agent 工具循环 → tool_trace == []。"""
    (debug_env / "douyin" / "faq.yaml").write_text(
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
        encoding="utf-8",
    )
    result = resolve_reply("douyin", "营业时间", debug=True, debug_token="tok-faq-tt")
    assert result["source"] == "faq"
    assert result["tool_trace"] == []


def test_non_debug_call_no_tool_trace(debug_env: Path) -> None:
    """非 debug 调用方：不进诊断分支，返回结构不含 tool_trace（零回归）。"""
    result = resolve_reply("douyin", "你好", recipient="user_1")
    assert "tool_trace" not in result
    assert "diagnostics" not in result
