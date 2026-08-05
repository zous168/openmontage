"""接管态 inbound 跳过 AI 自动回复."""

from fastapi.testclient import TestClient

from plugins.mxai.conversations.service import (
    get_conversation_mode,
    list_messages,
    set_conversation_mode,
)
from plugins.mxai.worklog.service import append_worklog


def test_inbound_skips_ai_when_takeover(mxai_client: TestClient, mxai_env) -> None:
    peer = "takeover_peer"
    conv_id = f"C-{peer}"
    append_worklog(
        profile_id="qiyeweixin",
        op_type="inbound_reply",
        exec_status="成功",
        op_object=f"{peer} · 问:你好 · 答:Bot 历史回复",
        data_dir=mxai_env,
    )
    set_conversation_mode("qiyeweixin", conv_id, "takeover", data_dir=mxai_env)

    before = len(list_messages("qiyeweixin", conv_id, data_dir=mxai_env))
    res = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"message_id": "m1", "sender": peer, "message": "新问题"},
    )
    assert res.status_code == 200
    assert res.json().get("status") == "takeover"
    after = list_messages("qiyeweixin", conv_id, data_dir=mxai_env)
    assert len(after) == before + 1
    assert after[-1]["from"] == "user"
    assert after[-1]["text"] == "新问题"


def test_inbound_auto_after_release(mxai_client: TestClient, mxai_env) -> None:
    peer = "release_peer"
    conv_id = f"C-{peer}"
    set_conversation_mode("wechat", conv_id, "takeover", data_dir=mxai_env)
    mxai_client.post(
        f"/api/plugins/mxai/agents/wechat/conversations/{conv_id}/takeover",
        json={"takeover": False},
    )
    assert get_conversation_mode("wechat", conv_id, data_dir=mxai_env) == "auto"
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "m2", "sender": peer, "message": "咨询产品"},
    )
    assert res.status_code == 200
    assert res.json().get("status") != "takeover"
