"""仿爆款文案改写。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from plugins.mxai.content.copy_rewrite import parse_rewrite_payload, rewrite_viral_copy


def test_parse_rewrite_payload() -> None:
    raw = """
{
  "source_copy": {
    "full_script": "新口播全文",
    "hook": "新钩子",
    "cta": "新cta"
  },
  "shots": [
    {"id": 1, "copy": "镜1改写"},
    {"id": 2, "copy": "镜2改写"}
  ]
}
"""
    shots = [{"id": 1, "copy": "原1"}, {"id": 2, "copy": "原2"}]
    parsed = parse_rewrite_payload(raw, shots)
    assert parsed["source_copy"]["hook"] == "新钩子"
    assert len(parsed["shots"]) == 2
    assert parsed["shots"][0]["copy"] == "镜1改写"


def test_rewrite_mock(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = rewrite_viral_copy(
        source_copy={"hook": "原钩子", "full_script": "原口播"},
        shots=[{"id": 1, "copy": "原镜1"}],
        instruction="换成护肤品类",
    )
    assert out["mock"] is True
    assert out["model"]
    assert out["source_copy"]["hook"]
    assert out["shots"][0]["copy"]
    assert out["instruction"] == "换成护肤品类"


def test_rewrite_empty_raises() -> None:
    with pytest.raises(HTTPException) as ei:
        rewrite_viral_copy(source_copy={}, shots=[{"id": 1, "copy": ""}])
    assert ei.value.status_code == 422
