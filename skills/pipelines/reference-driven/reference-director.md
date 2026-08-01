# Reference Director — Reference-Driven Pipeline

## When to Use

You are the **Reference Director** — the first stage of the `reference-driven` pipeline.
The user chose this pipeline because they have an **inspiration video** and want a
**differentiated version**, not a pixel-perfect clone.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Meta skill | `skills/meta/video-reference-analyst.md` | **Read and follow this entire skill** |
| Bootstrap | `projects/<id>/meta.json` → `production_inputs` | Reference URL/path, topic, platform |
| Schema | `schemas/artifacts/video_analysis_brief.schema.json` | Output artifact |

## Process

1. Read `meta.json` → `production_inputs` for:
   - `reference_url` and/or `reference_media_path` (project-relative after bootstrap)
   - `topic` — what the user's version is about
   - `target_platform`, `target_duration_seconds`, `preferred_output_pipeline` (if set)

2. **Follow `skills/meta/video-reference-analyst.md` end-to-end** for the reference
   source. Use the URL or the on-disk reference file under `projects/<id>/`.

3. Write a schema-valid **`video_analysis_brief`** artifact and checkpoint for stage
   `reference_analysis`.

4. Present the conversational 5-aspect summary to the user **before** marking the
   stage complete. Do not skip capability audit or critical questions from the meta skill.

5. If `preferred_output_pipeline` is not `auto`, note it in `replication_guidance` but
   still recommend the best pipeline honestly when tools or motion type disagree.

## Output

- `artifacts/video_analysis_brief.json` (canonical)
- `checkpoint_reference_analysis.json` with status appropriate to policy

Downstream stages (`research`, `proposal`, …) consume this brief. Do **not** collapse
into later stages — this checkpoint is the contract gate for reference-driven work.
