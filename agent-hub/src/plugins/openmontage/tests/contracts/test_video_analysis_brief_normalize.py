"""video_analysis_brief beat.kind alias normalization."""

from __future__ import annotations

from plugins.openmontage.schemas.artifacts import (
    normalize_artifact,
    validate_artifact,
)
from plugins.openmontage.tests.contracts.test_phase0_contracts import sample_artifact


def test_push_alias_normalizes_to_camera_before_validate() -> None:
    data = sample_artifact("video_analysis_brief")
    scenes = data["structure_analysis"]["scenes"]
    scenes[0]["beats"] = [
        {
            "start_seconds": 0,
            "end_seconds": 1.5,
            "kind": "push",
            "description": "slow push-in on product",
        }
    ]
    validate_artifact("video_analysis_brief", data)
    assert scenes[0]["beats"][0]["kind"] == "camera"


def test_normalize_artifact_maps_common_camera_verbs() -> None:
    data = sample_artifact("video_analysis_brief")
    scenes = data["structure_analysis"]["scenes"]
    scenes[0]["beats"] = [
        {
            "start_seconds": 0,
            "end_seconds": 1,
            "kind": "dolly",
            "description": "dolly in",
        }
    ]
    normalize_artifact("video_analysis_brief", data)
    assert scenes[0]["beats"][0]["kind"] == "camera"
