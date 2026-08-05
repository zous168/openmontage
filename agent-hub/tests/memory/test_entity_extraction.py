"""Entity plausibility filters for holographic memory."""

from __future__ import annotations

from plugins.memory.holographic.store import MemoryStore, is_plausible_entity


def test_is_plausible_entity_rejects_shell_errors() -> None:
    assert not is_plausible_entity("File not found")
    assert not is_plausible_entity("cd: No such file or directory")
    assert not is_plausible_entity("bash: command not found")
    assert not is_plausible_entity("ERROR: something failed")


def test_is_plausible_entity_accepts_real_names() -> None:
    assert is_plausible_entity("Douyin")
    assert is_plausible_entity("John Doe")
    assert is_plausible_entity("Marketing Hub")


def test_add_fact_skips_junk_entities(tmp_path) -> None:
    db = tmp_path / "memory_store.db"
    store = MemoryStore(db_path=str(db))
    store.add_fact('Shell failed with "File not found" on deploy', category="general")
    store.add_fact('平台 "Douyin" 的评论规则', category="general")
    store.close()

    conn = __import__("sqlite3").connect(db)
    names = [row[0] for row in conn.execute("SELECT name FROM entities ORDER BY name")]
    conn.close()
    assert "Douyin" in names
    assert "File not found" not in names
