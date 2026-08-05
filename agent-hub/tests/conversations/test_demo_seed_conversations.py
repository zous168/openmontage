"""demo_seed 公域/Boss Q&A 会话."""

from plugins.mxai.cfg.bootstrap.demo_seed import seed_demo_data
from plugins.mxai.conversations.service import list_conversations, list_messages


def test_seed_public_conversations(mxai_env) -> None:
    seed_demo_data(mxai_env, force=True)
    dy = list_conversations("douyin", data_dir=mxai_env)
    assert len(dy) >= 2
    xhs = list_conversations("xiaohongshu", data_dir=mxai_env)
    assert len(xhs) >= 1
    sph = list_conversations("shipinhao", data_dir=mxai_env)
    assert len(sph) >= 1


def test_seed_boss_conversation_messages(mxai_env) -> None:
    seed_demo_data(mxai_env, force=True)
    boss = list_conversations("boss", data_dir=mxai_env)
    assert len(boss) >= 2
    li = next(c for c in boss if "前端-李工" in c["name"] or "前端-李工" in c["id"])
    msgs = list_messages("boss", li["id"], data_dir=mxai_env)
    assert len(msgs) >= 2
    assert msgs[0]["from"] == "user"
