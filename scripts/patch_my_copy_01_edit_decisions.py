"""Patch my-copy-01 edit_decisions with complete Remotion props for Studio preview."""

from __future__ import annotations

import json
from pathlib import Path

from tools.video.remotion_caption_burn import RemotionCaptionBurn

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "my-copy-01"
EDIT_PATH = PROJECT / "artifacts" / "edit_decisions.json"
SCRIPT_PATH = PROJECT / "artifacts" / "script.json"
TRANSCRIPT_PATH = PROJECT / "assets" / "audio" / "narration_transcript.json"

# Whisper misreads vs script ground truth
WORD_CORRECTIONS = {
    "模片": "馍片",
    "回勾": "回购",
    "花焦": "花椒",
}


def build_overlays(script: dict, segments: list[dict]) -> list[dict]:
    sections = script.get("sections") or []
    overlays: list[dict] = []
    for index, section in enumerate(sections):
        seg = segments[index] if index < len(segments) else None
        start = float(seg["start"]) if seg else float(section.get("start_seconds") or 0)
        end = float(seg["end"]) if seg else float(section.get("end_seconds") or start + 2)
        overlays.append(
            {
                "id": section.get("id") or f"overlay-{index}",
                "type": "section_title",
                "in_seconds": round(start, 3),
                "out_seconds": round(end, 3),
                "text": section.get("label") or f"§{index + 1}",
                "subtitle": "",
                "position": "top-left",
            }
        )
    return overlays


def build_captions(segments: list[dict]) -> list[dict]:
    tool = RemotionCaptionBurn()
    return tool._segments_to_word_captions(segments, WORD_CORRECTIONS)


def main() -> None:
    edit = json.loads(EDIT_PATH.read_text(encoding="utf-8"))
    script = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))
    transcript = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
    segments = transcript.get("segments") or []

    overlays = build_overlays(script, segments)
    captions = build_captions(segments)

    meta = dict(edit.get("metadata") or {})
    meta["remotion_overlays"] = overlays
    meta["remotion_captions"] = captions
    edit["metadata"] = meta
    edit["overlays"] = overlays

    audio = dict(edit.get("audio") or {})
    narration = dict(audio.get("narration") or {})
    narration["src"] = "assets/audio/narration_remotion48k.wav"
    narration["volume"] = narration.get("volume", 1.0)
    audio["narration"] = narration
    edit["audio"] = audio

    subs = dict(edit.get("subtitles") or {})
    subs["enabled"] = True
    subs["style"] = "word-by-word"
    subs["source"] = "assets/subtitles/narration.srt"
    subs.setdefault("position", "bottom-center")
    subs.setdefault("max_words_per_line", 6)
    edit["subtitles"] = subs

    EDIT_PATH.write_text(json.dumps(edit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Patched {EDIT_PATH}")
    print(f"  overlays: {len(overlays)} (labels: {[o['text'] for o in overlays]})")
    print(f"  captions: {len(captions)} words")
    print(f"  narration: {narration['src']}")


if __name__ == "__main__":
    main()
