"""CR-121 LT-034.05.1：流式应答生成器 resolve_reply_stream.

覆盖：① LLM 经 Hermes 流式（delta≥1 + tool 实时 + done 含 diagnostics/tool_trace）；
② FAQ / KB 即时命中（整段 delta + done，tool_trace=[]）；③ done 后调试会话已落本轮
（record_debug_turn 生效）。复用 hermes_agent._iter_parsed_sse_events 构造 Hermes SSE 流帧。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.mxai.agents import hermes_agent
from plugins.mxai.agents.pipeline import resolve_reply_stream

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


def _sse_lines_with_tool_run() -> list[str]:
    """Hermes SSE：tool.started → tool.completed → delta×2 → run.completed(含 transcript)。"""
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
        'data: {"tool_name":"kb_search","duration":0.512,"is_error":false}',
        "",
        "event: assistant.delta",
        'data: {"delta":"已为您"}',
        "",
        "event: assistant.delta",
        'data: {"delta":"查询。"}',
        "",
        "event: run.completed",
        f"data: {json.dumps(transcript, ensure_ascii=False)}",
        "",
    ]


def _patch_hermes(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
    """patch Hermes 事件流。

    真实 Hermes /chat/stream 会按传入 ``session_id`` 服务端持久化本轮；为忠实模拟该副作用
    （CR-119 LT-034.01.6 后 pipeline 不再对 agent_* 源 record_debug_turn，依赖 Hermes 自身落库），
    本 stub 捕获传入的 session_id 并把 user+assistant 写进对应会话，断言「落库恰好一次」才成立。
    """

    def _fake(profile_id, message, *, session_id=None, session_key=None, **k):
        if session_id is not None:
            # 模拟 Hermes 服务端按传入 session 持久化本轮（user + 聚合 assistant 全文）
            full = "".join(
                str(ev.get("delta") or "")
                for ev in hermes_agent._iter_parsed_sse_events(iter(lines))
                if ev.get("event") == "delta"
            )
            db = hermes_agent._profile_session_db(profile_id)
            try:
                hermes_agent._ensure_debug_session(db, session_id)
                db.append_message(session_id, "user", message)
                if full:
                    db.append_message(session_id, "assistant", full)
            finally:
                db.close()
        return hermes_agent._iter_parsed_sse_events(iter(lines))

    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.iter_profile_agent_events", _fake
    )


# ─── ① LLM 流式：delta + tool 实时 + done ───


def test_stream_llm_yields_delta_tool_done(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: [])
    _patch_hermes(monkeypatch, _sse_lines_with_tool_run())

    events = list(
        resolve_reply_stream("douyin", "支持本地部署吗", debug_token="tok-stream-1")
    )
    types = [e["type"] for e in events]

    # delta ≥ 1（边出边显）
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) >= 1
    assert "".join(d["text"] for d in deltas) == "已为您查询。"

    # tool 事件实时推送（含 seq/name）
    tools = [e for e in events if e["type"] == "tool"]
    assert any(t["step"]["name"] == "kb_search" for t in tools)
    started = next(t for t in tools if t["step"].get("input") is not None)
    assert started["step"]["seq"] == 1
    assert started["step"]["name"] == "kb_search"

    # 末帧 done：含 diagnostics + 完整 tool_trace（带 output）
    assert types[-1] == "done"
    done = events[-1]
    assert "diagnostics" in done
    diag = done["diagnostics"]
    for key in ("source", "faq", "kb_hits", "risk", "sensitive_hits", "model", "timing_ms",
                "tokens", "memory_rounds"):
        assert key in diag
    trace = done["tool_trace"]
    assert len(trace) == 1
    assert trace[0]["name"] == "kb_search"
    assert trace[0]["output"] == "命中 3 条切片…"  # output 到 done 才补全
    assert trace[0]["duration_ms"] == 512  # 流内 completed.duration 回填


def test_stream_tool_started_has_live_fields_output_deferred(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """live tool.started 带 name/input，output 暂缺（到 done 的 tool_trace 才补）。"""
    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: [])
    _patch_hermes(monkeypatch, _sse_lines_with_tool_run())
    events = list(resolve_reply_stream("douyin", "q", debug_token="tok-live"))
    started = next(
        e for e in events if e["type"] == "tool" and e["step"].get("input") is not None
    )
    assert started["step"]["input"] == json.dumps({"query": "本地部署"}, ensure_ascii=False)
    assert started["step"]["output"] is None  # live 阶段 output 不可得


# ─── ② FAQ / KB 即时命中：整段 delta + done(tool_trace=[]) ───


def test_stream_faq_instant_hit(debug_env: Path) -> None:
    (debug_env / "douyin" / "faq.yaml").write_text(
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
        encoding="utf-8",
    )
    events = list(resolve_reply_stream("douyin", "营业时间", debug_token="tok-faq"))
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"] == "9 点到 18 点"  # 整段一帧
    done = events[-1]
    assert done["type"] == "done"
    assert done["diagnostics"]["source"] == "faq"
    assert done["tool_trace"] == []
    assert not [e for e in events if e["type"] == "tool"]


def test_stream_kb_injected_not_direct(debug_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-125：流式下知识库**不直接回复**——KB 命中作 top-X 注入，回复来自大模型。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1: [{"text": "KB 命中片段", "file_path": "inline:doc1", "score": 0.9}],
    )
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.iter_profile_agent_events", lambda *a, **k: iter([])
    )
    events = list(resolve_reply_stream("douyin", "随便问", debug_token="tok-kb"))
    deltas = [e for e in events if e["type"] == "delta"]
    full = "".join(d["text"] for d in deltas)
    assert full and full != "KB 命中片段"          # 回复来自 mock LLM，非 KB 原文直答
    assert "已参考知识库" in full                    # mock LLM 标记：KB 上下文已注入
    done = events[-1]
    assert done["diagnostics"]["source"] == "llm"   # 不再是 "kb"
    assert done["diagnostics"]["kb_hits"]            # KB 命中仍入诊断（注入上下文）


def test_stream_sensitive_blocked(debug_env: Path) -> None:
    (debug_env / "douyin" / "sensitive_words.yaml").write_text(
        "words:\n  - 违禁词\n", encoding="utf-8"
    )
    events = list(resolve_reply_stream("douyin", "这是违禁词测试", debug_token="tok-sens"))
    deltas = [e for e in events if e["type"] == "delta"]
    assert deltas and "拦截" in deltas[0]["text"]
    done = events[-1]
    assert done["diagnostics"]["source"] == "sensitive_blocked"
    assert done["diagnostics"]["sensitive_hits"] == ["违禁词"]


# ─── ③ done 后调试会话已落本轮（record_debug_turn 生效） ───


def test_stream_persists_debug_turn(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: [])
    _patch_hermes(monkeypatch, _sse_lines_with_tool_run())
    token = "tok-persist"
    list(resolve_reply_stream("douyin", "支持本地部署吗", debug_token=token))

    sid = hermes_agent.debug_session_id("douyin", token)
    db = hermes_agent._profile_session_db("douyin")
    try:
        assert db.get_session(sid) is not None
        msgs = db.get_messages(sid)
    finally:
        db.close()
    contents = [m.get("content") or "" for m in msgs]
    assert any("支持本地部署吗" in c for c in contents)
    assert any("已为您查询。" in c for c in contents)
    # 落库恰好一次：Hermes 自身落 debug 会话，pipeline 不再对 agent_* 双写 → 仅 1 轮（2 条）
    assert len(msgs) == 2


def test_stream_faq_persists_debug_turn(debug_env: Path) -> None:
    (debug_env / "douyin" / "faq.yaml").write_text(
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
        encoding="utf-8",
    )
    token = "tok-faq-persist"
    list(resolve_reply_stream("douyin", "营业时间", debug_token=token))
    sid = hermes_agent.debug_session_id("douyin", token)
    db = hermes_agent._profile_session_db("douyin")
    try:
        msgs = db.get_messages(sid)
    finally:
        db.close()
    contents = [m.get("content") or "" for m in msgs]
    assert any("9 点到 18 点" in c for c in contents)


# ─── ④ Hermes 不可用（mock 默认）→ 退回整段 delta + done ───


def test_stream_fallback_to_mock_single_delta(debug_env: Path) -> None:
    """无 patch Hermes（mock 无 API key → iter_profile_agent_events 空）→ 整段一帧 + done。"""
    events = list(resolve_reply_stream("douyin", "随便聊聊", debug_token="tok-mock"))
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) == 1
    assert deltas[0]["text"]
    done = events[-1]
    assert done["type"] == "done"
    assert done["tool_trace"] == []


# ─── ⑤ CR-119 LT-034.01.6：流式 debug LLM 走 :debug: 隔离会话/记忆键 ───


def test_stream_llm_passes_debug_session_id_and_key(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """流式 LLM 分支把 session_id（含 ``-debug-``）/ session_key（含 ``:debug:``）
    传给 iter_profile_agent_events——而非 inbound-default。"""
    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1: [])
    captured: dict[str, object] = {}

    def _spy(profile_id, message, *, recipient="", session_id=None, session_key=None,
             session_title=None, **k):
        captured.update(
            session_id=session_id, session_key=session_key, session_title=session_title
        )
        return hermes_agent._iter_parsed_sse_events(iter(_sse_lines_with_tool_run()))

    monkeypatch.setattr("plugins.mxai.agents.pipeline.iter_profile_agent_events", _spy)

    token = "tok-route-stream"
    list(resolve_reply_stream("douyin", "支持本地部署吗", debug_token=token))

    assert captured["session_id"] == hermes_agent.debug_session_id("douyin", token)
    assert captured["session_key"] == hermes_agent.debug_session_key("douyin", token)
    assert "-debug-" in str(captured["session_id"])
    assert ":debug:" in str(captured["session_key"])
    assert captured["session_title"] == "调试客户"


def test_stream_does_not_write_inbound_default(debug_env: Path) -> None:
    """流式 mock 兜底落 debug 会话；inbound-default 恒不被创建/写入。"""
    pid, token = "douyin", "tok-stream-no-inbound"
    inbound_default_sid = hermes_agent.inbound_session_id(pid, "")

    list(resolve_reply_stream(pid, "随便聊聊", debug_token=token))

    db = hermes_agent._profile_session_db(pid)
    try:
        assert db.get_session(inbound_default_sid) is None
        # 本轮落 debug 会话（mock 兜底经 record_debug_turn）
        assert len(db.get_messages(hermes_agent.debug_session_id(pid, token))) == 2
    finally:
        db.close()


def test_stream_two_tokens_isolated(debug_env: Path) -> None:
    """两个不同 token 流式各发一轮 → 各自 debug 会话历史互不可见（mock 兜底路径）。"""
    pid = "douyin"
    list(resolve_reply_stream(pid, "A 流式消息", debug_token="tok-sA"))
    list(resolve_reply_stream(pid, "B 流式消息", debug_token="tok-sB"))

    db = hermes_agent._profile_session_db(pid)
    try:
        a = [m.get("content") or "" for m in db.get_messages(
            hermes_agent.debug_session_id(pid, "tok-sA"))]
        b = [m.get("content") or "" for m in db.get_messages(
            hermes_agent.debug_session_id(pid, "tok-sB"))]
    finally:
        db.close()
    assert any("A 流式消息" in c for c in a) and not any("B 流式消息" in c for c in a)
    assert any("B 流式消息" in c for c in b) and not any("A 流式消息" in c for c in b)
