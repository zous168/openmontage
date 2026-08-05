"""Tests for LLM request debug logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.llm_request_log import (
    record_llm_api_request_from_agent,
    serialize_error_payload,
    serialize_request_payload,
    serialize_response_payload,
)
from hermes_state import SessionDB


class _FakeAgent:
    def __init__(self, db: SessionDB, session_id: str) -> None:
        self._session_db = db
        self._session_db_created = True
        self.session_id = session_id
        self.provider = "openai"
        self.base_url = "https://api.example.com/v1"
        self.model = "gpt-test"
        self.api_mode = "chat_completions"
        self.api_key = "sk-test-secret-key"

    def _ensure_db_session(self) -> None:
        self._session_db.ensure_session(self.session_id, source="test")


@pytest.fixture
def session_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionDB:
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    db = SessionDB(db_path=db_path)
    db.ensure_session("sess-1", source="test")
    yield db
    db.close()


def test_serialize_request_redacts_api_key() -> None:
    payload = serialize_request_payload(
        {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}], "api_key": "sk-secret"}
    )
    data = json.loads(payload)
    assert data["model"] == "gpt-test"
    assert "secret" not in data["api_key"]


def test_serialize_response_payload() -> None:
    payload = serialize_response_payload({"choices": [{"message": {"content": "ok"}}]})
    assert payload is not None
    assert json.loads(payload)["choices"][0]["message"]["content"] == "ok"


def test_serialize_error_payload() -> None:
    payload = serialize_error_payload(RuntimeError("boom"), details="invalid response")
    data = json.loads(payload or "{}")
    assert data["details"] == "invalid response"
    assert data["type"] == "RuntimeError"


def test_record_and_list_llm_api_request(session_db: SessionDB) -> None:
    agent = _FakeAgent(session_db, "sess-1")
    record_llm_api_request_from_agent(
        agent,
        api_request_id="turn-1:api:1",
        turn_id="turn-1",
        api_call_count=1,
        attempt=1,
        api_kwargs={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
        response={"choices": [{"message": {"content": "world"}}]},
        status="success",
        latency_ms=1234.0,
        input_tokens=10,
        output_tokens=5,
    )

    items = session_db.list_llm_api_requests("sess-1")
    assert len(items) == 1
    assert items[0]["status"] == "success"
    assert items[0]["input_tokens"] == 10

    detail = session_db.get_llm_api_request("sess-1", items[0]["id"])
    assert detail is not None
    request = json.loads(detail["request_json"])
    assert request["messages"][0]["content"] == "hello"
    response = json.loads(detail["response_json"])
    assert response["choices"][0]["message"]["content"] == "world"


def test_delete_session_removes_llm_logs(session_db: SessionDB) -> None:
    agent = _FakeAgent(session_db, "sess-1")
    record_llm_api_request_from_agent(
        agent,
        api_request_id="turn-1:api:2",
        turn_id="turn-1",
        api_call_count=2,
        attempt=1,
        api_kwargs={"model": "gpt-test", "messages": []},
        response={"ok": True},
        status="success",
        latency_ms=50.0,
    )
    assert session_db.count_llm_api_requests("sess-1") == 1
    assert session_db.delete_session("sess-1")
    assert session_db.count_llm_api_requests("sess-1") == 0
