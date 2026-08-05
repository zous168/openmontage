"""助理 LLM：mock 兜底 + 营销 profile SOUL 注入路径.

CR-125：助理 real 模式已**统一走 profile agent 链路**（不再有 ``_assistant_messages``
直连 ``call_llm`` 的特殊链路），故原 ``test_assistant_real_uses_main_model_*`` 随死代码移除；
「用主模型而非标题模型」的关注点现由 Hermes ``assistant`` Profile 的模型配置承担。
"""

from types import SimpleNamespace

from plugins.mxai.agents import assistant as assistant_mod
from plugins.mxai.agents import hermes_agent


def test_assistant_mock_when_mxai_mock(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")

    result = assistant_mod.complete_assistant_reply("随便问一句", [])
    assert result["source"] == "assistant_mock"
    assert "工作台助理" in result["text"]


def test_marketing_real_uses_profile_soul_in_system_prompt(monkeypatch, mxai_env) -> None:
    del mxai_env
    from hermes_cli.profiles import get_profile_dir
    from plugins.mxai.cfg.prompt_config import SOUL_FILE

    soul_path = get_profile_dir("douyin") / SOUL_FILE
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text("你是抖音专属客服小抖，语气活泼。", encoding="utf-8")

    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setattr(hermes_agent, "resolve_llm_mode", lambda: "real")
    monkeypatch.setattr(hermes_agent, "iter_profile_agent_events", lambda *a, **k: iter([]))
    calls: list[dict] = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="好的亲～"))]
        )

    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call_llm)

    result = hermes_agent.complete_profile_agent_reply(
        "douyin", "多少钱", recipient="u1", allow_fallback=True
    )
    assert result["text"] == "好的亲～"
    assert calls
    system = calls[0]["messages"][0]["content"]
    assert "抖音专属客服小抖" in system
