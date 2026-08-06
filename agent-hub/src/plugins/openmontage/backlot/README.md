# Backlot — the living storyboard

A production board mounted into the Hermes hub that shows a production
happening — and, since API v44, can **drive** it: pipeline stages lighting up,
the script as a screenplay page, the scene plan as a filmstrip that fills in as
assets generate, decisions, spend, and activity — all derived from what the
pipeline already writes to `projects/<id>/`.

| Surface | Hub path |
|---|---|
| Library / board / flow UI | `/plugins/openmontage/` |
| API / SSE / media / thumb | `/api/plugins/openmontage/` |

There is **no** standalone `backlot open` / `backlot serve` process. Open the
hub and navigate to `/plugins/openmontage/`.

For local TestClient / tooling, `create_app()` still builds a temporary FastAPI
app with the classic `/api/...` and `/` paths.

## Driving a stage from the page (in-process agent channel)

The board's "运行下一阶段" button runs an in-process Hermes `AIAgent` to execute
exactly one pipeline stage, then the page approves / rejects the gate — the same
contract as the interactive agent:

| Endpoint (under `/api/plugins/openmontage`) | Purpose |
|---|---|
| `POST /project/{id}/stage/run` | run in-process Hermes `AIAgent`. 202 + `task_id`. 400 if `stage != get_next_stage()`; 409 if a run is active |
| `GET /project/{id}/stage/runs` | recent runs (+ `log_tail`) |
| `GET /project/{id}/stage/run/{task_id}/log` | incremental log lines |
| `POST /project/{id}/stage/run/{task_id}/cancel` | `agent.interrupt()`; patches a stuck `in_progress` to `failed` |
| `POST /project/{id}/stage/approve` | `awaiting_human → completed` (`human_approved=True`) + mirrored `user_approved=true` decision |
| `POST /project/{id}/stage/reject` | `human_rejection` decision + stage back to `in_progress` (artifacts kept), feedback fed to the next run |

Run progress lives in `projects/<id>/runs/<task_id>.json` (heartbeats every
~25s) — the same watcher → SSE → board path, so no extra polling. A
`.run.lock` file makes the web channel self-serializing (stale takeover);
`reconcile_runs()` marks leftover `running` tasks failed after a server
restart (in-process agents cannot be reattached).

## How it stays live

A `watchfiles` watcher on `projects/` publishes change
notifications over SSE; the browser refetches board state. State sources:

| Board element | Disk source |
|---|---|
| identity / rail order | `project.json` + `pipeline_defs/<type>.yaml` |
| stage states, gates, versions | `checkpoint_<stage>.json` + `history/` |
| script card / modal | `artifacts/script.json` |
| filmstrip cards | `scene_plan × script × asset_manifest` join |
| generating shimmer, activity | `events.jsonl` (written by `BaseTool` instrumentation) |
| cost meter | checkpoint `cost_snapshot` |
| renders | `renders/*.mp4` (+ root-level mp4 heuristic) |

Projects without checkpoints degrade gracefully to a "what the watcher
found" view — media, snapshots, renders.

**Replay**: a completed run can be scrubbed end-to-end (▶ REPLAY RUN on the
board) — reconstructed from checkpoint history and event timestamps.

Try it without a real production (demo projects are **hidden from the library**;
open them by ID):

```bash
python scripts/backlot_simulate_run.py          # live demo run (~1 min)
# then open /plugins/openmontage/p/backlot-demo-run on the hub
python scripts/backlot_simulate_run.py --cleanup  # remove demo dir after
```

Design doc: `internal/design/LIVING_STORYBOARD.md`.
