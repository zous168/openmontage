# Backlot — the living storyboard

A local board that shows a production happening — and, since API v44, can
**drive** it: pipeline stages lighting up, the script as a screenplay page,
the scene plan as a filmstrip that fills in as assets generate, decisions,
spend, and activity — all derived from what the pipeline already writes to
`projects/<id>/`.

```bash
python -m plugins.openmontage.backlot open <project-id>   # start server if needed + open browser
python -m plugins.openmontage.backlot open                # library view (all projects)
python -m plugins.openmontage.backlot serve --port 4750   # run the server in the foreground
```

## Driving a stage from the page (headless agent channel)

The board's "运行下一阶段" button spawns a headless agent to execute exactly
one pipeline stage, then the page approves / rejects the gate — the same
contract as the interactive agent:

| Endpoint | Purpose |
|---|---|
| `POST /api/project/{id}/stage/run` | spawn `claude -p` (prompt via stdin: director skill + project status + manifest stage + feedback). 202 + `task_id`. 400 if `stage != get_next_stage()`; 409 if a run is active |
| `GET /api/project/{id}/stage/runs` | recent runs (+ `log_tail`) |
| `GET /api/project/{id}/stage/run/{task_id}/log` | incremental log lines |
| `POST /api/project/{id}/stage/run/{task_id}/cancel` | kill process tree; patches a stuck `in_progress` to `failed` |
| `POST /api/project/{id}/stage/approve` | `awaiting_human → completed` (`human_approved=True`) + mirrored `user_approved=true` decision |
| `POST /api/project/{id}/stage/reject` | `human_rejection` decision + stage back to `in_progress` (artifacts kept), feedback fed to the next run |

Run progress lives in `projects/<id>/runs/<task_id>.json` (heartbeats every
~25s) — the same watcher → SSE → board path, so no extra polling. A
`.run.lock` file makes the web channel self-serializing (stale takeover);
`reconcile_runs()` re-attaches to live processes after a server restart.

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
open them by ID or run simulate with `--cleanup` when done):

```bash
python scripts/backlot_simulate_run.py          # live demo run (~1 min)
python -m plugins.openmontage.backlot open backlot-demo-run         # board only — not in library grid
python scripts/backlot_simulate_run.py --cleanup  # remove demo dir after
```

Design doc: `internal/design/LIVING_STORYBOARD.md`.
