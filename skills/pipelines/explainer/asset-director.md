# Asset Director — Explainer Pipeline

## When to Use

You are the Asset Producer for a generated explainer video. You have a `scene_plan` with required assets and a `script` with narration text. Your job is to generate every asset needed: narration audio, images, diagrams, code snippets, and background music. Every file must exist on disk before you finish.

This is where plans become real files. A missing or low-quality asset will torpedo the final video.

## Animation authoring — which runtime

Before authoring any animated Remotion component for this pipeline, read **`skills/meta/animation-runtime-selector.md`**. It's the routing authority for deciding between Remotion primitives and GSAP plugins.

Quick routing for common explainer needs:

| Scene type | Recommended approach |
|---|---|
| Title card, fade, slide, scale | Remotion primitives — `interpolate()` + `spring()` |
| Word-level caption highlight synced to narration | Existing `CaptionOverlay` component (already in `remotion-composer/src/components/`) |
| Per-character kinetic typography ("words explode in one letter at a time") | GSAP SplitText — read `.agents/skills/gsap-plugins/SKILL.md` |
| Multi-step choreography across 4+ tweens | GSAP timeline — read `.agents/skills/gsap-timeline/SKILL.md` |
| Logo build (line drawing, stroke reveal) | GSAP DrawSVG — read `.agents/skills/gsap-plugins/SKILL.md` |
| Data chart (bar/line/pie/KPI) | Remotion built-in chart components — see `remotion-composer/SCENE_TYPES.md` |
| Terminal or CLI demo | Remotion TerminalScene — read `.agents/skills/synthetic-screen-recording/SKILL.md` |

**The keep-it-simple bias:** if Remotion primitives solve a scene in ≤ 20 lines, use them. Only pull in GSAP when the plugin genuinely earns its bundle weight.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]`, `state.artifacts["proposal"]["proposal_packet"]` | What to produce |
| Reference-driven (when present) | `state.artifacts["video_analysis_brief"]` | DNA lock, `generation`, per-scene analysis + beats |
| Deliverable | `projects/<id>/meta.json` → `production_inputs` (aspect ratio via `lib.deliverable_spec.resolve_deliverable`) | Aspect ratio locked at generation time |
| Playbook | Active style playbook | Image prompts, diagram style, audio preferences |
| Tools | `tts_selector`, `image_selector`, `video_selector`, `diagram_gen`, `code_snippet`, `music_gen` — selectors auto-discover all available providers from the registry | Generation capabilities |
| Cost tracker | `tools/cost_tracker.py` | Budget governance |

## Process

### Step 1: Inventory Required Assets

Walk every scene in the scene plan. For each `required_assets` entry, create an asset task:

```
Asset Task:
  scene_id: scene-3
  type: diagram
  description: "Mermaid flowchart: query -> encode -> search -> rank -> return"
  source: generate
  tool: diagram_gen
  estimated_cost: $0.00
```

Also create tasks for:
- **Narration audio** — one per script section (use `tts_selector` or a concrete TTS provider)
- **Background music** — one track for the whole video (use `music_gen` or select from library)
- **Sound effects** — per playbook's `sfx_style` (optional, use `music_gen` or stock)

### Step 2: Check Budget

Before generating anything:
1. Sum all estimated costs from the asset tasks
2. Compare against the cost tracker's remaining budget
3. If over budget:
  - Switch expensive tools to cheaper alternatives (use `tts_selector` with `preferred_provider` to route to cheaper TTS; use `image_selector` to route to cheaper image providers)
   - Reduce image count (combine similar scenes)
   - Skip optional assets (SFX, B-roll)
4. Get cost approval via cost tracker before proceeding

### Step 2b: Sample Preview (Prevents Wasted Spend)

Before batch-generating assets, produce one sample of each expensive asset type and present them to the user for approval:

1. **TTS sample**: Generate narration for `script.voice_performance.sample_section_id` when present; otherwise pick the section with the most demanding delivery. Play it for the user. Confirm voice, pace, pauses, emphasis, and tone are acceptable before generating the rest.
2. **Image sample**: Generate one image for the most representative scene. Show it to the user. Confirm the style, quality, and prompt approach before batch-generating all images.
3. **Music sample** (if using `music_gen`): Generate one short clip. Confirm mood and energy before committing.

If the user rejects a sample:
- Adjust the parameters (voice, prompt style, provider) and regenerate the sample.
- Do not batch-generate until the sample is approved.
- Max 3 sample iterations per asset type before escalating to the user for a decision.

This step typically costs $0.03–0.08 total and prevents $1–3 of wasted generation.

### Step 3: Generate Narration

For each script section:
1. Extract the narration text
2. Read `script.voice_performance` and section `delivery_cues`
3. Use `delivery_cues.provider_text` when present; otherwise transform the section text with purposeful punctuation and break tags only when the selected provider supports them
4. Apply speaker directions from the script (pace, emphasis, emotion)
5. Apply the playbook's `audio.voice_style`
6. Map cues to provider parameters:
   - OpenAI: `instructions` only with `model: "gpt-4o-mini-tts"`; use `response_format` for output format
   - Google TTS: `input_type: "ssml"` when using `<break>` tags, plus `speaking_rate` in `0.25..2.0` and `pitch` in `-20..20`
   - ElevenLabs: `stability`, `similarity_boost`, `style`, `speed`, and `use_speaker_boost`
7. Generate using `tts_selector` — it auto-routes to the best available TTS provider based on user preference and availability. Check the registry's `best_for` fields to understand each provider's strengths.
8. Record the applied `voice_performance` metadata on each narration asset
   (`generation_summary` must include provider + `length_scale`; never record
   `atempo fit` unless user approved faster speech in `decision_log`)

### Listenability (Binding)

Before batch TTS, read `script.voice_performance.provider_notes`. For Piper,
use **at least** the script's `length_scale` and **never below 0.85**. If
narration duration exceeds scene timing, extend the edit timeline or shorten
copy — do not accelerate speech to force-fit.
9. Verify the audio file exists and duration matches expected timing (±15%)

**Pronunciation guide**: If the script contains technical terms, jargon, or names with non-obvious pronunciation, include a pronunciation map in the TTS request.

**Flat voice failure:** If the approved voice sounds monotone, robotic, rushed,
or ignores intended pauses, do not batch the remaining sections. Revise the
`voice_performance` plan or provider parameters and regenerate the sample.

### Step 4: Generate Visual Assets

Process asset tasks grouped by tool for efficiency:

**Images (`image_selector`)** — explainer illustrations / diagrams-as-image:

1. Build the prompt from the scene's actual purpose:
   - scene-specific shot/lighting/texture cues from `shot_language`, `shot_intent`, and `texture_keywords`
   - an adapted visual anchor from the playbook or custom identity
   - the concrete subject/action/environment
   Use `lib/shot_prompt_builder.py` when helpful.
2. Add negative prompt from playbook
3. Include consistency anchors (same character/world/palette family), but do NOT reuse the exact same phrasing for every image
4. Generate and verify the file exists
5. If the result doesn't match expectations, refine the prompt and regenerate (max 2 retries)

> **Scope split:** Flat-motion / educational `image_selector` jobs use the playbook +
> five-aspect CHAI review below. **Reference-driven UGC / native phone footage** that
> will feed `video_selector` (or I2V keyframes meant to match reference motion) MUST
> follow **Video generation (`video_selector`)** and **Appendix A** instead — do not
> apply commercial explainer illustration defaults to those shots.

**Video generation (`video_selector`)** — reference-driven / UGC native fidelity:

> **This is the enforcement gate.** Final per-shot prompts are assembled HERE, at
> tool call time — not in scene-director. Every call gets a **complete, standalone**
> prompt. Silent omission and cross-shot shorthand ("same as above", "inherit previous prompt") are
> **forbidden**.
>
> **Tool-level enforcement:** When this block applies, you **MUST** pass
> `"prompt_profile": "ugc_native"` on every `video_selector` call. The selector
> **rejects** non-compliant prompts before any video model runs. Fix validation errors
> and retry — do not bypass by omitting `prompt_profile` or calling a provider directly.

**When this block applies (mandatory `prompt_profile: ugc_native`):**

- Scene `required_assets` specifies `tool: video_selector`, or `motion_type` /
  scene type is `generated` / `broll` / `image_animation` with motion required
- OR `video_analysis_brief` exists (reference-driven pipeline)
- **Does NOT apply** to `diagram_gen`, Remotion `.tsx` animations, TTS, or flat
  motion-graphics `image_selector` jobs (use `"prompt_profile": "default"` or omit)

**Before each `video_selector` call (blocking workflow):**

1. **Gather inputs** for this scene:
   - Matching row in `scene_plan.scenes[]`
   - **If `required_assets[].description` already contains the reverse-engineered UGC prompt**
     (`Aspect ratio:` or `[INHERIT DNA LOCK]`), use it verbatim as `final_prompt` — do not
     rewrite into generic English summaries
   - `video_analysis_brief.replication_guidance.playbook_customizations.dna_lock`
   - Matching `structure_analysis.scenes[]` entry (second-level beats, overlays, narration)
   - Otherwise call `lib.generation_spec.prompt_for_time_range()` or
     `segment_prompt_from_brief()` (reads `generation` + scene `beats[]`); UGC six-block validation
     applies only when `prompt_profile` is `ugc_native`
   - **Aspect ratio** from `meta.json` → `resolve_deliverable(production_inputs)["aspect_ratio"]`
   - Optional draft from `lib/shot_prompt_builder.build_scene_storyboard_prompt()` — treat as
     input only; you MUST expand to a full compliant prompt below

2. **Write the FINAL prompt** — every shot MUST include **all six** blocks, spelled out
   in full (no references to other shots):

   | # | Block | Requirement |
   |---|--------|-------------|
   | 1 | **Aspect ratio** | Explicit ratio (e.g. `9:16 vertical`, `16:9 horizontal`) from deliverable spec |
   | 2 | **Scene clutter / lighting / noise floor** | Foreground/midground clutter, light direction + quality, sensor/floor noise, room ambience — not a sterile set |
   | 3 | **Form strategy** | Capture mode: e.g. smartphone handheld UGC, selfie arm-length, table POV — state it explicitly |
   | 4 | **Second-level timed actions** | `[MM:SS-MM:SS]` beats with duration; micro-dynamics in gaps (breath, blink, finger adjust, fabric sway) |
   | 5 | **Physics / speed control** | `real-time physics`, `constant speed`, `no time-lapse`, `no dead frames`; DNA / consistency tokens from brief |
   | 6 | **Native imperfections** | Handheld micro-shake, focus breathing, uneven exposure, natural skin texture, visible grain — NOT beauty-polished |

3. **Run Appendix A** prohibition checklist — any hit requires rewrite before calling the tool.

4. **Run Pre/Post Self-Review** (below) using the six-block table + Appendix A, not the
   generic educational-image checklist alone.

5. **Pre-validate locally (recommended):**

```python
from lib.video_prompt_validator import validate_ugc_video_prompt
errors = validate_ugc_video_prompt(final_prompt, aspect_ratio="9:16")
assert not errors, errors
```

6. **Call `video_selector`** — required input shape when this block applies:

```json
{
  "prompt": "<full post-caption prompt with all six blocks>",
  "prompt_profile": "ugc_native",
  "aspect_ratio": "9:16",
  "operation": "text_to_video",
  "duration": "13"
}
```

   If validation fails, the tool returns `validation_errors` — expand the prompt and retry.
   **Do not** call `seedance_video`, `kling_official_video`, or any other video provider
   directly to skip validation.

7. **Record** the exact `prompt` sent on the asset manifest entry (`assets[].prompt`) plus
   `source_tool: "video_selector"` and `prompt_profile: ugc_native` in `generation_summary`
   for audit.

**Multi-segment reference videos (>13s dense motion):**

- Prefer `lib.generation_spec.segment_prompt_from_brief()` as the spine —
  call `segment_prompt_from_brief()` or use `assembled_prompt` when cached.
- Still re-validate all six blocks and Appendix A per call — do not assume the sidecar is
  complete without your pass.
- Segment 2+ must declare DNA inheritance and seamless continuation from the prior segment
  (character, scene, noise floor, audio continuity) when the brief requires it.

**Diagrams (`diagram_gen`)**:
1. Convert the scene description into valid Mermaid syntax
2. Apply playbook's `asset_generation.diagram_style`
3. Generate SVG/PNG
4. Verify all nodes and edges are present

**Code snippets (`code_snippet`)**:
1. Extract language and code from the scene description
2. Apply syntax highlighting theme from playbook's overlay styles
3. Generate highlighted image or Remotion-compatible data

### Step 5: Generate Music

1. Read playbook's `audio.music_mood` and `audio.music_volume`
2. Check the music decision from `proposal_packet.production_plan.music_source` (set by the Proposal Director)
3. Source the background track in this priority order:
   - **User-selected library track**: If the proposal specified a track from `music_library/`, copy it to `projects/<project>/assets/music/background_music.mp3`
   - **User music library (`music_library/`)**: If the folder exists and has tracks, pick the best match for the playbook's `audio.music_mood`. List candidates by filename and let the EP decide.
   - **Music generation API**: Use `music_gen` (ElevenLabs) or `suno_music` if available. Check status via registry first — if the tool is unavailable or quota-exhausted, skip immediately (do NOT attempt and fail silently).
   - **No music available**: Log this clearly in the asset manifest as `"music_status": "unavailable"` with the reason. Do NOT silently produce a video without music — the EP and user should know.
4. Duration should be at least as long as total video duration. If shorter, it can be looped by the compose stage.
5. Verify the audio file exists at `projects/<project>/assets/music/background_music.mp3`

**Critical:** If music generation fails or is unavailable, report it immediately in the asset manifest — do not defer the problem to the compose stage.

### Step 6: Build Asset Manifest

Assemble all generated assets into the manifest:

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "narration-s1",
      "type": "audio",
      "subtype": "narration",
      "path": "assets/narration/s1.mp3",
      "source_tool": "tts_selector",
      "scene_id": "scene-1",
      "duration_seconds": 8.2,
      "cost_usd": 0.003
    },
    {
      "id": "img-scene-3",
      "type": "image",
      "path": "assets/images/scene-3-diagram.png",
      "source_tool": "diagram_gen",
      "scene_id": "scene-3",
      "cost_usd": 0.00
    },
    {
      "id": "music-bg",
      "type": "audio",
      "subtype": "music",
      "path": "assets/music/background.mp3",
      "source_tool": "music_gen",
      "duration_seconds": 62,
      "cost_usd": 0.05
    }
  ],
  "total_cost_usd": 0.053,
  "generation_summary": {
    "narration_sections": 5,
    "images_generated": 8,
    "diagrams_generated": 2,
    "music_tracks": 1
  }
}
```

### Pre/Post Self-Review for Generation Prompts

> Before sending a prompt to any generation tool — `image_selector`, `diagram_gen`, `video_selector`, even `code_snippet` styling prompts — run a three-step self-review modeled on the CHAI oversight loop ("Building a Precise Video Language with Human-AI Oversight", arXiv 2604.21718v2). Cost is small (no extra tool calls); benefit is large (avoids wasted generations).
>
> **Routing:** For **`video_selector`** (reference-driven / UGC native), Step 2 critique MUST use the **six-block table + Appendix A** in Step 4 above — not the generic five-aspect explainer checklist alone. For `diagram_gen`, flat-motion `image_selector`, and `code_snippet`, use the five-aspect checklist below.
>
> **Step 1 — Pre-caption pass.** Write the prompt the way you'd write it today. Do not over-edit; aim for a complete first draft.
>
> **Step 2 — Critique pass.** Score the draft against the 5-aspect checklist (Subject / Subject Motion / Scene / Spatial Framing / Camera). For each aspect:
> - Is it specified? If not, is the omission deliberate (e.g., "Camera N/A — Remotion native scene", "no subject motion — static diagram") or accidental?
> - Are confusable terms disambiguated? (dolly vs zoom, pan vs truck, bird's-eye vs aerial, fisheye vs barrel, full shot vs close-up; for diagrams: flowchart vs sequence vs state diagram, top-down vs left-right)
> - Are emotional adjectives ("clean", "professional", "modern") replaced with their visual causes (sans-serif typography, generous whitespace, monochromatic palette with one accent)?
> - For multi-shot prompts: is identity anchored verbatim across shots? For `image_selector` prompts that recur (a character or world appearing in multiple scenes), are consistency anchors specified verbatim?
>
> **Step 3 — Post-caption pass.** Rewrite filling the missing aspects, fixing confusable terms, and replacing subjective language. The post-caption is what gets sent to the generation tool.
>
> Log the (pre, critique, post) triplet in the asset metadata for traceability. This mirrors the CHAI workflow and creates a record the reviewer can audit.

### Step 7: Verify All Assets

**Existence check:**
- [ ] Every asset `path` exists on disk
- [ ] Every narration section has a corresponding audio file
- [ ] Every scene with `required_assets` has all assets generated
- [ ] Background music file exists

**Quality check:**
- [ ] Narration durations within ±15% of expected timing
- [ ] Narration assets record `voice_performance.delivery_cues_applied`
- [ ] Approved TTS sample uses the same provider, voice, and expressive settings as the batch
- [ ] Images match the playbook's style (review consistency anchors)
- [ ] Diagrams are legible and complete
- [ ] Total cost within budget

### Step 8: Self-Evaluate

Score (1-5):

| Criterion | Question |
|-----------|----------|
| **Completeness** | Does every scene have all required assets? |
| **Audio quality** | Does narration sound natural with correct pacing? |
| **Visual consistency** | Do all images look like they belong to the same video? |
| **Budget adherence** | Is total cost within the approved budget? |
| **Playbook fidelity** | Do assets match the playbook's style guide? |

If any dimension scores below 3, fix before proceeding.

### Step 9: Submit

Validate the asset_manifest against the schema and persist via checkpoint.

### Mid-Production Fact Verification

If you encounter uncertainty during asset generation:
- Use `web_search` to verify visual accuracy of subjects (e.g. what does this building actually look like?)
- Use `web_search` to find reference images before generating illustrations
- Log verification in the decision log: `category="visual_accuracy_check"`

Visual accuracy matters. If the script mentions a specific place, person, or object,
verify what it actually looks like before generating images. Don't rely on
the AI model's training data — it may be wrong or outdated.

## Common Pitfalls

- **Generating before checking budget**: Always estimate total cost first. A 60-second video with 15 images can burn $3+ quickly.
- **Inconsistent image style**: Each image_selector call is independent. Use consistent anchors, but adapt them per scene. If you paste the same style prefix into every prompt, the video will feel machine-made and repetitive.
- **Ignoring narration timing**: If TTS produces 12s of audio for a 10s section, the edit phase will struggle. Check durations. **Do NOT** fix timing by speeding up TTS beyond the listenability floor (`length_scale` ≥ 0.85 for Piper, no post-TTS `atempo` squeeze). Extend cuts or trim copy instead — see `skills/meta/voice-performance-director.md` → Listenability Floor.
- **Ignoring delivery cues**: Generating raw script text when `provider_text` or `delivery_cues` exist will flatten the read. Apply the voice-performance contract first.
- **Missing pronunciation guide**: "PostgreSQL" or "Kubernetes" will be mispronounced without explicit guidance.
- **One retry then give up**: If an image doesn't match, refine the prompt specifically — don't just retry the same prompt.
- **AI-generating images with exact text (CTA, business names, contact info)**: AI image models frequently hallucinate wrong text — wrong business name, wrong phone number, misspelled words. **Never use AI image generation for scenes where text must be verbatim.** Use Remotion `text_card` type instead. This applies to: CTA screens, title cards with business names, contact info overlays, legal disclaimers. If a scene's `type` is `text_card` in the scene plan, do NOT generate an image for it — skip it and let the compose stage render it natively in Remotion.


## When You Do Not Know How

If you encounter a generation technique, provider behavior, or prompting pattern you are unsure about:

1. **Search the web** for current best practices — models and APIs change frequently, and the agent's training data may be stale
2. **Check `.agents/skills/`** for existing Layer 3 knowledge (provider-specific prompting guides, API patterns)
3. **If neither helps**, write a project-scoped skill at `projects/<project-name>/skills/<name>.md` documenting what you learned
4. **Reference source URLs** in the skill so the knowledge is traceable
5. **Log it** in the decision log: `category: "capability_extension"`, `subject: "learned technique: <name>"`

This is especially important for:
- **Video generation prompting** — models respond to specific vocabularies that change with each version
- **Image model parameters** — optimal settings for FLUX, GPT Image, Imagen differ and evolve
- **Audio provider quirks** — voice cloning, music generation, and TTS each have model-specific best practices
- **Remotion component patterns** — new composition techniques emerge as the framework evolves

Do not rely on stale knowledge. When in doubt, search first.

---

## Appendix A — UGC / reference video generation prohibitions (binding)

**Applies only when calling `video_selector`** (and UGC-fidelity `image_selector` keyframes
that must match reference motion). Does **not** apply to Remotion scenes, diagrams, or
flat-motion explainer illustrations.

### Ultimate enforcement (non-negotiable)

- Do **not** omit any segment of visual detail — every segment fully specified
- Do **not** simplify handheld bumpiness — do not smooth out handheld shake
- Do **not** remove native noise — preserve sensor grain and room noise floor
- Do **not** ship incomplete segment replication — incomplete replication is a blocking failure
- Do **not** use "same as above" or "inherit previous prompt" without re-stating all six blocks
- **Must** execute the six-block table in full before every `video_selector` call

### Strictly forbidden in prompts and acceptable output targets

**Visual / render style — do NOT produce or prompt for:**

- AI-generated virtual humans, CGI, 3D modeling, anime / 2D stylization
- Heavy beauty filter / skin smoothing, flawless fake pale skin, plastic fake skin
- Perfect symmetrical composition, sterile empty scenes, ultra-clean sharpening
- Professional cinema lighting, even perfect softbox fill, studio / commercial blockbuster look
- Photo-retouch / studio glamour aesthetic, influencer hyper-saturated filters
- Zero-noise pristine frames, germ-free tidy sets, dreamlike bokeh backgrounds
- Gimbal-smooth / steadicam-stable camera (unless reference explicitly shows it — default is handheld native)
- Exquisite modeled hair strands, "Doubao AI" plastic texture look

**Motion / continuity — do NOT allow:**

- Segment face drift, scene swaps mid-clip, prop add/remove vs locked DNA
- Sudden lighting jumps, quality/style breaks between segments
- Stiff posed mannequin acting, aspect ratio inconsistency across shots
- Lip-sync mismatch, physically impossible object interaction

**Audio (when the provider supports embedded audio prompts) — do NOT prompt for:**

- Robotic / mechanical AI voice, flat emotionless delivery
- Foreign accent when reference is native speaker, stiff announcer delivery
- Pitch/timbre discontinuity across segments when continuity is required

When in doubt, describe **positive native alternatives** (handheld phone capture, visible grain,
natural skin texture, cluttered real environment, real-time physics) instead of negative lists alone.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
