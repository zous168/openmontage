# /backlot — open the living storyboard

Open the Backlot board (browser UI showing pipeline stages, script, scene plan, and generated assets live) for the requested project:

- With project id → hub path `/plugins/openmontage/p/<project-id>`
- No project id → library `/plugins/openmontage/`
- Prefer telling the user the hub URL (e.g. `http://127.0.0.1:8643/plugins/openmontage/`). There is no separate `backlot open` process.
- If it fails, report and continue — the board is an observer, never a blocker.
- The board derives all state from `projects/<id>/` on disk; never update the UI manually. Keep checkpoints and artifacts honest per `skills/meta/checkpoint-protocol.md`.
