#!/usr/bin/env python3
"""Generate image + narration assets for my-copy-01 (c1, 图生, 豆包 TTS).

OPENMONTAGE_NON_PRODUCTION_SCRIPT — dev/dogfood utility only. Production
assets must come from the assets stage via asset-director + registry tools.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-hub" / "src"))

PROJECT = ROOT / "projects" / "my-copy-01"
IMG_DIR = PROJECT / "assets" / "images"
AUDIO_DIR = PROJECT / "assets" / "audio"

SCENE_PROMPTS = {
    "sc1": (
        "Vertical 9:16 food product photo: Chinese snack bag pouring golden crispy "
        "Sichuan pepper flatbread chips into an open palm over woven straw placemat, "
        "warm indoor lifestyle lighting, appetizing, shallow depth of field, "
        "yellow packaging with Chinese text, professional Douyin snack ad style"
    ),
    "sc2": (
        "Vertical 9:16 product shot: two Chinese snack packages side by side, "
        "green bag labeled pepper fragrance flavor and yellow bag spicy flavor, "
        "花椒馍片 style packaging, red manicured hand holding them, warm lighting"
    ),
    "sc3": (
        "Vertical 9:16 close-up Chinese snack package 花椒馍片, net weight 128g visible, "
        "诸葛卧龙 brand style, crisp packaging details, warm food photography"
    ),
    "sc4": (
        "Vertical 9:16 extreme close-up single golden crispy bread chip coated with "
        "Sichuan pepper honey glaze and spices, held between fingers, macro food photography"
    ),
    "sc5": (
        "Vertical 9:16 close-up hands with red nail polish breaking a golden crispy "
        "bread chip in half showing airy crunchy cross-section, shallow DOF, food ASMR style"
    ),
    "sc6": (
        "Vertical 9:16 close-up hand holding a single golden pepper bread chip near camera, "
        "warm appetizing snack photography, vertical TikTok framing"
    ),
    "sc7": (
        "Vertical 9:16 macro stack of golden crispy Chinese bread chips showing texture "
        "and pepper seasoning, food photography, warm tones"
    ),
    "sc8": (
        "Vertical 9:16 top-down lifestyle food shot: bamboo basket full of golden "
        "花椒馍片 chips on wooden desk with small calendar and cute tiger figurine, "
        "warm saturated colors, Douyin snack showcase"
    ),
}

NARRATION = (
    "上次买的花椒馍片又回购了，128g双口味直接囤。"
    "有椒香和麻辣两种口味。"
    "上面裹了花椒蜜。"
    "口感特别的酥脆。"
    "越嚼越香。"
    "真的太好吃了，点击小黄车。"
)


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    from plugins.openmontage.tools.graphics.image_selector import ImageSelector
    from plugins.openmontage.tools.audio.tts_selector import TTSSelector

    assets: list[dict] = []
    total_cost = 0.0
    image_tool = ImageSelector()

    for scene_id, prompt in SCENE_PROMPTS.items():
        out = IMG_DIR / f"{scene_id}.png"
        print(f"[image] {scene_id} ...")
        if out.exists() and out.stat().st_size > 1000:
            print(f"  skip existing {out.name}")
            assets.append({
                "id": f"img_{scene_id}",
                "type": "image",
                "path": f"assets/images/{scene_id}.png",
                "source_tool": "image_selector",
                "scene_id": scene_id,
                "prompt": prompt,
                "cost_usd": 0.0,
            })
            continue
        result = image_tool.execute({
            "prompt": prompt,
            "width": 768,
            "height": 1344,
            "aspect_ratio": "9:16",
            "output_path": str(out),
        })
        if not result.success:
            print(f"  FAIL: {result.error}")
            return 1
        cost = float(result.cost_usd or 0)
        total_cost += cost
        rel = f"assets/images/{scene_id}.png"
        if result.data.get("path"):
            rel_path = Path(result.data["path"])
            if rel_path.exists() and rel_path != out:
                out.write_bytes(rel_path.read_bytes())
        assets.append({
            "id": f"img_{scene_id}",
            "type": "image",
            "path": rel,
            "source_tool": result.data.get("provider") or "image_selector",
            "scene_id": scene_id,
            "prompt": prompt,
            "model": result.model,
            "cost_usd": cost,
            "resolution": "768x1344",
        })
        print(f"  ok ({cost:.3f} USD)")

    narr_path = AUDIO_DIR / "narration.mp3"
    print("[tts] narration ...")
    tts = TTSSelector()
    tts_result = tts.execute({
        "preferred_provider": "doubao",
        "text": NARRATION,
        "output_path": str(narr_path),
        "enable_timestamp": True,
    })
    if not tts_result.success:
        print(f"  FAIL: {tts_result.error}")
        return 1
    tts_cost = float(tts_result.cost_usd or 0)
    total_cost += tts_cost
    assets.append({
        "id": "narr_full",
        "type": "narration",
        "path": "assets/audio/narration.mp3",
        "source_tool": tts_result.data.get("provider") or "doubao_tts",
        "scene_id": "sc1",
        "cost_usd": tts_cost,
        "duration_seconds": tts_result.data.get("duration_seconds"),
    })
    print(f"  ok ({tts_cost:.3f} USD)")

    manifest = {
        "version": "1.0",
        "assets": assets,
        "total_cost_usd": round(total_cost, 4),
        "metadata": {
            "visual_source": "image_gen",
            "tts_provider": "doubao",
            "concept_id": "c1",
        },
    }
    out_manifest = PROJECT / "artifacts" / "asset_manifest.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {len(assets)} assets, ${total_cost:.4f} -> {out_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
