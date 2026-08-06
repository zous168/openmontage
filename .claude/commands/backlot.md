---
description: Open the Backlot living storyboard — the browser board that shows pipeline stages, script, scene plan, and generated assets live as a production runs.
argument-hint: [project-id (optional — defaults to the library)]
---

Open the Backlot board for the requested project in the Hermes hub browser:

- With project id → open `/plugins/openmontage/p/<project-id>`
- No argument → open the library: `/plugins/openmontage/`
- Prefer telling the user the hub URL (e.g. `http://127.0.0.1:8643/plugins/openmontage/`). There is no separate `backlot open` process.
- If the board cannot open, report it and continue — the board is an observer, never a blocker.
- The board derives everything from disk (`projects/<id>/` checkpoints, artifacts, assets, events). You never update the UI manually; keep checkpoints and artifacts honest per `skills/meta/checkpoint-protocol.md`.
