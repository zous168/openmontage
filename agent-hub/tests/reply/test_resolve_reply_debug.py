"""resolve_reply debug 模式 + 诊断增强（CR-119 / LT-034.01.2）.

向后兼容地为 ``resolve_reply`` 加 debug 能力：debug 持久化走 ``record_debug_turn``
（不写 inbound），返回附 07 §2.9a 形状的 ``diagnostics``；``bypass_faq/kb`` 旁路。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.agents import hermes_agent
from plugins.mxai.agents.pipeline import resolve_reply

_SIX_CHANNELS = ("douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss")


@pytest.fixture
def debug_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离数据根 + profiles；KB 落同一 hub 根（CR-165 FAQ/话术分区）。"""
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for name in _SIX_CHANNELS:
        p = profiles / name
        p.mkdir()
        (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    get_dir = lambda name: profiles / name  # noqa: E731
    monkeypatch.setattr("plugins.mxai.agents.pipeline.get_profile_dir", get_dir)
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", get_dir)
    from plugins.mxai.cfg.paths import mxai_db_path
    from plugins.mxai.kb.service import ensure_business_partitions
    from plugins.mxai.kb.storage.kb_repo import init_kb_schema
    from plugins.mxai.kb.worker import KbWorker

    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    ensure_business_partitions(data_dir)
    return data_dir


def _write(data_root: Path, profile_id: str, filename: str, content: str) -> None:
    """写渠道 cfg；若为 faq.yaml 则改为种子 KB「FAQ/话术」（CR-165）。"""
    if filename == "faq.yaml":
        _seed_faq_from_yaml(data_root, content)
        return
    path = data_root / "profiles" / profile_id / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_faq_from_yaml(data_root: Path, yaml_text: str) -> None:
    import yaml

    from plugins.mxai.kb.faq_scripts import import_faq_excel
    from plugins.mxai.kb.partition_scope import get_faq_scripts_partition
    from plugins.mxai.kb.service import ensure_business_partitions
    from openpyxl import Workbook
    import io

    ensure_business_partitions(data_root)
    part = get_faq_scripts_partition(data_dir=data_root)
    assert part is not None
    data = yaml.safe_load(yaml_text) or {}
    entries = data.get("entries") or []
    wb = Workbook()
    ws = wb.active
    ws.append(["question", "answer"])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # match: exact 仅精准：测试侧用「问法=答案原文」再加一条不会模糊命中的问法——简化：全量导入
        q = str(entry.get("question") or entry.get("q") or "").strip()
        a = str(entry.get("answer") or entry.get("a") or "").strip()
        if q and a:
            ws.append([q, a])
    buf = io.BytesIO()
    wb.save(buf)
    import_faq_excel(int(part["partition_id"]), buf.getvalue(), data_dir=data_root)


def test_six_channels_debug_have_reply_and_diagnostics(debug_env: Path) -> None:
    for ch in _SIX_CHANNELS:
        result = resolve_reply(ch, "你好啊", debug=True, debug_token=f"tok-{ch}")
        assert result.get("text"), f"{ch} 应有非空 reply"
        diag = result.get("diagnostics")
        assert isinstance(diag, dict), f"{ch} 应含 diagnostics"
        assert diag["source"] == result["source"]
        # 真实测量的 timing 总耗时存在
        assert diag["timing_ms"]["total"] is not None
        # 必备键齐全
        for key in ("faq", "kb_hits", "risk", "sensitive_hits", "model", "tokens", "memory_rounds"):
            assert key in diag


def test_diagnostics_source_faq_exact(debug_env: Path) -> None:
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
    )
    result = resolve_reply("douyin", "营业时间", debug=True, debug_token="tok-faq")
    assert result["source"] == "faq"
    assert result["text"] == "9 点到 18 点"
    diag = result["diagnostics"]
    assert diag["source"] == "faq"
    assert diag["faq"]["question"] == "营业时间"
    # CR-165：id 为 chunk_id；精准 score=1.0 / match=exact
    assert diag["faq"]["id"]
    assert diag["faq"]["score"] == 1.0
    assert diag["faq"]["match"] == "exact"
    assert diag["timing_ms"]["faq"] is not None


# ─── CR-119 LT-034.01.5.2：FAQ 模糊匹配 + 相似度 score（FR-FAQ-03 精准+模糊双匹配）───


def test_faq_fuzzy_hit_near_input(debug_env: Path) -> None:
    """近似输入 → 模糊命中：match="fuzzy"、score 在 (阈值,1) 区间且 <1，仍 source=faq。"""
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 能优惠吗\n    answer: 近期有活动\n",
    )
    result = resolve_reply("douyin", "能不能优惠", debug=True, debug_token="tok-fz")
    assert result["source"] == "faq"
    assert result["text"] == "近期有活动"
    diag = result["diagnostics"]["faq"]
    assert diag["match"] == "fuzzy"
    assert diag["question"] == "能优惠吗"
    assert 0.6 <= diag["score"] < 1.0


def test_faq_exact_preferred_over_fuzzy(debug_env: Path) -> None:
    """精准优先：存在精准条目时命中精准（score=1.0/exact），不被模糊条目抢占。"""
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        (
            "entries:\n"
            "  - id: f1\n    question: 能优惠吗\n    answer: 模糊答案\n"
            "  - id: e1\n    question: 能不能优惠\n    answer: 精准答案\n"
        ),
    )
    result = resolve_reply("douyin", "能不能优惠", debug=True, debug_token="tok-exf")
    assert result["text"] == "精准答案"
    diag = result["diagnostics"]["faq"]
    assert diag["match"] == "exact"
    assert diag["score"] == 1.0


def test_faq_below_threshold_falls_through_no_misfire(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """低于阈值不误命中 FAQ → 落 KB/LLM（防线上误答回归）。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1, partition_ids=None: [],
    )
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 能优惠吗\n    answer: 近期有活动\n",
    )
    result = resolve_reply("douyin", "今天天气怎么样", debug=True, debug_token="tok-low")
    assert result["source"] == "llm"
    # 未命中 FAQ → diag.faq 为 None（未误填）
    assert result["diagnostics"]["faq"] is None


def test_faq_fuzzy_hit_does_not_call_kb(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BR-01/BR-23：模糊命中 FAQ 后不调 KB。"""
    called = {"kb": False}

    def _spy(q, limit=1, partition_ids=None):
        called["kb"] = True
        return []

    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", _spy)
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 能优惠吗\n    answer: 近期有活动\n",
    )
    result = resolve_reply("douyin", "能不能优惠", debug=True, debug_token="tok-nokb")
    assert result["source"] == "faq"
    assert called["kb"] is False


def test_faq_score_real_nonnull_on_hit(debug_env: Path) -> None:
    """debug 诊断 faq.score 真实非 null（精准=1.0、模糊为真实比率）。"""
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
    )
    exact = resolve_reply("douyin", "营业时间", debug=True, debug_token="tok-s1")
    assert exact["diagnostics"]["faq"]["score"] is not None


def test_faq_exact_only_entry_excluded_from_fuzzy(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-165：KB FAQ 问法均参与模糊；本用例改为「无相近问法时不命中」。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1, partition_ids=None: [],
    )
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - id: q1\n    question: 完全不相干的专有名词XYZ\n    answer: 近期有活动\n",
    )
    result = resolve_reply("douyin", "能不能优惠", debug=True, debug_token="tok-exonly")
    assert result["source"] == "llm"


def test_diagnostics_source_kb(debug_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_hit = {
        "text": "本地部署支持纯离线运行。",
        "file_path": "inline:产品手册",
        "score": 0.83,
        "partition_id": "产品手册",
        "doc_id": "d_07",
        "seq": 12,
        "matched_via": "intent",
    }
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1, partition_ids=None: [fake_hit],
    )
    result = resolve_reply("douyin", "支持本地部署吗", debug=True, debug_token="tok-kb")
    # CR-125：知识库**不直接回复**——KB 命中作 top-X 注入上下文 + 诊断，回复来自大模型。
    assert result["source"] == "llm"          # 不再是 "kb"
    diag = result["diagnostics"]
    assert diag["source"] == "llm"
    assert len(diag["kb_hits"]) == 1          # KB 命中仍入诊断（作注入/检索上下文）
    hit = diag["kb_hits"][0]
    assert hit["partition"] == "产品手册"
    assert hit["doc_id"] == "d_07"
    assert hit["seq"] == 12
    assert hit["score"] == 0.83
    assert hit["matched_via"] == "intent"
    assert "本地部署" in hit["snippet"]
    assert diag["timing_ms"]["kb"] is not None
    assert "已参考知识库" in result["text"]    # mock LLM 标记：确证 KB 上下文已注入


def test_diagnostics_source_sensitive_blocked(debug_env: Path) -> None:
    _write(debug_env, "douyin", "sensitive_words.yaml", "words:\n  - 违禁词\n")
    result = resolve_reply("douyin", "这里有违禁词", debug=True, debug_token="tok-sens")
    assert result["source"] == "sensitive_blocked"
    diag = result["diagnostics"]
    assert diag["source"] == "sensitive_blocked"
    assert diag["sensitive_hits"] == ["违禁词"]
    assert diag["risk"]["action"] == "block"


def test_diagnostics_source_llm_fallback(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 无 FAQ/敏感词命中、KB 无命中 → 走 LLM（MXAI_MOCK=1 → source=llm）
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1, partition_ids=None: [],
    )
    result = resolve_reply("douyin", "随便聊聊天气", debug=True, debug_token="tok-llm")
    assert result["source"] == "llm"
    diag = result["diagnostics"]
    assert diag["source"] == "llm"
    assert diag["timing_ms"]["llm"] is not None
    assert diag["risk"]["action"] == "allow"


def test_bypass_faq_changes_source(debug_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(
        debug_env,
        "douyin",
        "faq.yaml",
        "entries:\n  - question: 营业时间\n    answer: 9 点到 18 点\n",
    )
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=1, partition_ids=None: [],
    )
    # 不旁路：命中 FAQ
    hit_faq = resolve_reply("douyin", "营业时间", debug=True, debug_token="t1")
    assert hit_faq["source"] == "faq"
    # 旁路 FAQ：同一输入改走 LLM 兜底（KB 空）
    bypassed = resolve_reply(
        "douyin", "营业时间", debug=True, debug_token="t1", bypass_faq=True
    )
    assert bypassed["source"] == "llm"
    assert bypassed["source"] != hit_faq["source"]


def test_model_from_override(debug_env: Path) -> None:
    result = resolve_reply(
        "douyin", "你好", debug=True, debug_token="t-ov", model_override="deepseek-chat"
    )
    assert result["diagnostics"]["model"]["from"] == "override"
    no_ov = resolve_reply("douyin", "你好", debug=True, debug_token="t-no")
    assert no_ov["diagnostics"]["model"]["from"] == "agent_bound"


def test_debug_persists_to_debug_session_not_inbound(debug_env: Path) -> None:
    pid = "douyin"
    token = "tok-persist"
    recipient_like = token  # 若误用 recipient 命名，inbound id 会以此 slug 生成

    resolve_reply(pid, "你好啊", debug=True, debug_token=token)

    debug_sid = hermes_agent.debug_session_id(pid, token)
    inbound_sid = hermes_agent.inbound_session_id(pid, recipient_like)

    db = hermes_agent._profile_session_db(pid)
    try:
        # 落 debug 会话，且 user_id 为 None（客户发现天然排除）
        dbg = db.get_session(debug_sid)
        assert dbg is not None
        assert dbg["user_id"] is None
        assert len(db.get_messages(debug_sid)) == 2  # user + assistant
        # 未写任何 inbound 会话
        assert db.get_session(inbound_sid) is None
    finally:
        db.close()


# ─── CR-119 LT-034.01.6：debug LLM 走 :debug: 隔离会话/记忆键（非 inbound-default）───


def test_debug_llm_passes_debug_session_id_and_key(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """debug LLM 调用须把 session_id（含 ``-debug-``）/ session_key（含 ``:debug:``）传给
    ``complete_profile_agent_reply``——而非 inbound-default。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1, partition_ids=None: []
    )
    captured: dict[str, object] = {}

    def _spy(pid, msg, *, recipient="", session_id=None, session_key=None,
             session_title=None, allow_fallback=False, **kw):
        captured.update(
            session_id=session_id,
            session_key=session_key,
            session_title=session_title,
            untrusted_customer=kw.get("untrusted_customer"),
            hermes_profile=pid,
        )
        return {"source": "llm", "text": "stub 应答"}

    monkeypatch.setattr("plugins.mxai.agents.pipeline.complete_profile_agent_reply", _spy)

    pid, token = "douyin", "tok-route"
    resolve_reply(pid, "随便聊聊", debug=True, debug_token=token)

    # 入站可能经 binding 解析到具体 Hermes profile（如 douyin_comment）
    bound = str(captured["hermes_profile"])
    assert captured["session_id"] == hermes_agent.debug_session_id(bound, token)
    assert captured["session_key"] == hermes_agent.debug_session_key(bound, token)
    assert "-debug-" in str(captured["session_id"])
    assert ":debug:" in str(captured["session_key"])
    assert captured["session_title"] == "调试客户"
    assert captured["untrusted_customer"] is True  # 入站仍包裹；诊断展示真实 API 请求


def test_debug_llm_does_not_write_inbound_default(debug_env: Path) -> None:
    """debug LLM（mock 路径）落 debug 会话；inbound-default 会话恒不被创建/写入。"""
    pid, token = "douyin", "tok-no-inbound"
    inbound_default_sid = hermes_agent.inbound_session_id(pid, "")  # mxai-douyin-inbound-default

    db = hermes_agent._profile_session_db(pid)
    try:
        before = db.get_session(inbound_default_sid)
    finally:
        db.close()
    assert before is None

    resolve_reply(pid, "你好啊", debug=True, debug_token=token)

    db = hermes_agent._profile_session_db(pid)
    try:
        # inbound-default 仍不存在（debug LLM 不再写它）
        assert db.get_session(inbound_default_sid) is None
        # 本轮落 debug 会话
        assert len(db.get_messages(hermes_agent.debug_session_id(pid, token))) == 2
    finally:
        db.close()


def test_debug_llm_hermes_source_persists_exactly_once(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """agent_* 源（Hermes 已自落 debug 会话）→ pipeline 不再 record_debug_turn（避免双写）。

    stub 模拟 Hermes 服务端按传入 session_id 落本轮，pipeline 不应再补记 → 恰好 2 条。
    """
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1, partition_ids=None: []
    )

    def _hermes_like(pid, msg, *, recipient="", session_id=None, session_key=None,
                     session_title=None, allow_fallback=False, **_):
        db = hermes_agent._profile_session_db(pid)
        try:
            hermes_agent._ensure_debug_session(db, session_id)
            db.append_message(session_id, "user", msg)
            db.append_message(session_id, "assistant", "Hermes 应答")
        finally:
            db.close()
        return {"source": "agent_llm", "text": "Hermes 应答"}

    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.complete_profile_agent_reply", _hermes_like
    )

    pid, token = "douyin", "tok-once"
    resolve_reply(pid, "随便聊聊", debug=True, debug_token=token)

    db = hermes_agent._profile_session_db(pid)
    try:
        msgs = db.get_messages(hermes_agent.debug_session_id(pid, token))
    finally:
        db.close()
    # 恰好一轮（user+assistant），无重复双写
    assert len(msgs) == 2


def test_two_debug_tokens_isolated_histories(debug_env: Path) -> None:
    """两个不同 debug token 各发消息 → 各自 debug 会话历史互不可见。"""
    pid = "douyin"
    resolve_reply(pid, "A 的专属消息", debug=True, debug_token="tok-A")
    resolve_reply(pid, "B 的专属消息", debug=True, debug_token="tok-B")

    db = hermes_agent._profile_session_db(pid)
    try:
        a_msgs = [m.get("content") or "" for m in db.get_messages(
            hermes_agent.debug_session_id(pid, "tok-A"))]
        b_msgs = [m.get("content") or "" for m in db.get_messages(
            hermes_agent.debug_session_id(pid, "tok-B"))]
    finally:
        db.close()

    assert any("A 的专属消息" in c for c in a_msgs)
    assert not any("B 的专属消息" in c for c in a_msgs)
    assert any("B 的专属消息" in c for c in b_msgs)
    assert not any("A 的专属消息" in c for c in b_msgs)


def test_non_debug_call_unchanged(debug_env: Path) -> None:
    """向后兼容：非 debug 调用返回结构不含 diagnostics，且持久化仍走 inbound。"""
    pid = "douyin"
    result = resolve_reply(pid, "你好", recipient="user_1")
    assert "diagnostics" not in result
    assert result.get("text")

    inbound_sid = hermes_agent.inbound_session_id(pid, "user_1")
    db = hermes_agent._profile_session_db(pid)
    try:
        assert db.get_session(inbound_sid) is not None
        # 未误写 debug 会话
        assert db.get_session(hermes_agent.debug_session_id(pid, "user_1")) is None
    finally:
        db.close()


# ─── CR-119 LT-034.01.5.1：model/token/matched_via 真实化遥测 ───


def test_diagnostics_model_and_tokens_passthrough_real(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入带 usage+model 的 LLM 结果 → 诊断 model.{provider,name}/tokens.{in,out} 透传真实值。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1, partition_ids=None: []
    )
    # 模拟真实模型应答：complete_profile_agent_reply 透出 model + 精确 tokens
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.complete_profile_agent_reply",
        lambda pid, msg, *, recipient="", allow_fallback=False, **_: {
            "source": "agent_llm",
            "text": "您好，这是真实模型应答。",
            "model": {"provider": "deepseek", "name": "deepseek-chat"},
            "tokens": {"in": 123, "out": 45},
        },
    )
    result = resolve_reply("douyin", "随便聊聊", debug=True, debug_token="tok-real")
    diag = result["diagnostics"]
    assert diag["model"]["provider"] == "deepseek"
    assert diag["model"]["name"] == "deepseek-chat"
    assert diag["tokens"] == {"in": 123, "out": 45}
    # 真实 token 不带估算标注
    assert "estimated" not in diag["tokens"]


def test_diagnostics_kb_matched_via_passthrough(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入带 matched_via 的 KB hit → 诊断 kb_hits[0].matched_via 透出真实值。"""
    fake_hit = {
        "text": "命中文本",
        "file_path": "inline:手册",
        "score": 0.9,
        "matched_via": "hybrid",
    }
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1, partition_ids=None: [fake_hit]
    )
    result = resolve_reply("douyin", "查询", debug=True, debug_token="tok-mv")
    # CR-125：KB 不直接回复（source=llm）；命中 matched_via 仍透传进诊断。
    assert result["source"] == "llm"
    assert result["diagnostics"]["kb_hits"][0]["matched_via"] == "hybrid"


def test_diagnostics_mock_model_nonnull_tokens_estimated(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MXAI_MOCK 路径：model.name 非 null（配置值）、tokens 非 null 且带 estimated 标注。"""
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks", lambda q, limit=1, partition_ids=None: []
    )
    # mock 下无真实模型 → name 回退 agent 配置 effective_model（真实配置值，注入稳定）
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_agent_model",
        lambda pid: {
            "effective_provider": "deepseek",
            "effective_model": "deepseek-chat",
        },
    )
    result = resolve_reply("douyin", "你好世界", debug=True, debug_token="tok-mock")
    assert result["source"] == "llm"
    diag = result["diagnostics"]
    # 配置名非 null
    assert diag["model"]["name"] == "deepseek-chat"
    assert diag["model"]["provider"] == "deepseek"
    # mock token 为估算值且明确标注
    assert diag["tokens"] is not None
    assert diag["tokens"]["estimated"] is True
    assert diag["tokens"]["in"] >= 1
    assert diag["tokens"]["out"] >= 1


# ── CR-125：会话方式 reply_mode + 知识库 top-X 注入 ──────────────────────────
def test_reply_mode_faq_first_keeps_faq_direct(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """faq_first（默认）：FAQ 精准命中仍直答（source=faq）。"""
    monkeypatch.setattr("plugins.mxai.agents.pipeline._read_reply_mode", lambda: "faq_first")
    _write(
        debug_env, "douyin", "faq.yaml",
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
    )
    result = resolve_reply("douyin", "营业时间", debug=True, debug_token="tok-ff")
    assert result["source"] == "faq"
    assert result["text"] == "9 点到 18 点"


def test_reply_mode_llm_unified_skips_faq_direct(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-125：llm_unified 下 FAQ 不直接命中即回复，转大模型（source=llm）。"""
    monkeypatch.setattr("plugins.mxai.agents.pipeline._read_reply_mode", lambda: "llm_unified")
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.kb_search_chunks",
        lambda q, limit=3, partition_ids=None: [],
    )
    _write(
        debug_env, "douyin", "faq.yaml",
        "entries:\n  - id: q1\n    question: 营业时间\n    answer: 9 点到 18 点\n",
    )
    result = resolve_reply("douyin", "营业时间", debug=True, debug_token="tok-lu")
    assert result["source"] == "llm"          # 非 faq（llm_unified 跳过直答）
    assert result["diagnostics"]["faq"] is None


def test_kb_inject_top_x_default_three(
    debug_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-125：知识库注入按 inject_top_x 取条数（默认 3）。"""
    captured: dict[str, Any] = {}

    def _spy(q, limit=1, partition_ids=None):
        captured["limit"] = limit
        return []

    monkeypatch.setattr("plugins.mxai.agents.pipeline.kb_search_chunks", _spy)
    resolve_reply("douyin", "随便问点什么", debug=True, debug_token="tok-tx")
    assert captured.get("limit") == 3
