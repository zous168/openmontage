"""Drive my-copy-01 reference-driven full chain via Backlot API (auto-approve gates).

Usage (hub on :8643):
  python -u scripts/_e2e_chain_verify.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / ".data"
BASE = "http://127.0.0.1:8643/api/plugins/openmontage"
PROJECT = "my-copy-01"
POLL_SEC = 20
MAX_WALL_SEC = 6 * 60 * 60


def _token() -> str:
    return (DATA / "device" / "local_ipc.token").read_text(encoding="utf-8").strip()


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE,
        headers={"X-Hub-Local-Token": _token()},
        timeout=60.0,
    )


def _status_local() -> dict:
    sys.path.insert(0, str(ROOT / "agent-hub" / "src"))
    from plugins.openmontage.lib.project_status import build_project_status

    return build_project_status(PROJECT)


def _busy(c: httpx.Client) -> dict | None:
    r = c.get(f"/project/{PROJECT}/stage/runs")
    r.raise_for_status()
    for run in r.json().get("runs") or []:
        if run.get("status") in ("queued", "running"):
            return run
    return None


def _approve(c: httpx.Client, stage: str) -> dict:
    r = c.post(
        f"/project/{PROJECT}/stage/approve",
        json={"stage": stage, "notes": "e2e auto-approve for chain verify"},
    )
    if r.status_code >= 400:
        raise RuntimeError(f"approve {stage}: {r.status_code} {r.text[:500]}")
    return r.json()


def _run(c: httpx.Client, stage: str) -> dict:
    r = c.post(f"/project/{PROJECT}/stage/run", json={"stage": stage})
    if r.status_code >= 400:
        raise RuntimeError(f"run {stage}: {r.status_code} {r.text[:800]}")
    return r.json()


def _reset(c: httpx.Client) -> dict:
    r = c.post(f"/project/{PROJECT}/pipeline/reset", json={})
    if r.status_code >= 400:
        raise RuntimeError(f"reset: {r.status_code} {r.text[:800]}")
    return r.json()


def main() -> int:
    started = time.time()
    print(f"==> health + reset + run full chain for {PROJECT}", flush=True)
    with _client() as c:
        h = c.get("/health")
        h.raise_for_status()
        print("health:", h.json(), flush=True)

        busy = _busy(c)
        if busy:
            tid = busy.get("task_id")
            print("cancel busy:", tid, busy.get("stage"), flush=True)
            if tid:
                c.post(f"/project/{PROJECT}/stage/run/{tid}/cancel")
                time.sleep(3)

        skip_reset = str(__import__("os").environ.get("OPENMONTAGE_E2E_SKIP_RESET") or "").strip() in (
            "1", "true", "yes",
        )
        if skip_reset:
            print("skip reset (OPENMONTAGE_E2E_SKIP_RESET)", flush=True)
            st0 = _status_local()
            next0 = st0.get("next_stage")
            gate0 = st0.get("gate_blocked")
            busy0 = _busy(c)
            if gate0 and not busy0:
                print("resume at gate; poller will auto-approve", flush=True)
            elif next0 and not busy0:
                print("kick:", _run(c, next0), flush=True)
            else:
                print(
                    f"resume without kick next={next0} gate={gate0} busy={busy0 and busy0.get('stage')}",
                    flush=True,
                )
        else:
            print("reset:", json.dumps(_reset(c), ensure_ascii=False)[:400], flush=True)
            print("kick:", _run(c, "reference_analysis"), flush=True)

        last_note = ""
        while True:
            elapsed = int(time.time() - started)
            if elapsed > MAX_WALL_SEC:
                print("FAIL: wall clock exceeded", flush=True)
                return 2

            st = _status_local()
            stages = {s["stage"]: s for s in st.get("stages") or []}
            next_stage = st.get("next_stage")
            gate = st.get("gate_blocked")
            suggested = st.get("suggested_action")
            completed = st.get("completed_stages") or []
            busy = _busy(c)

            note = (
                f"t={elapsed}s next={next_stage} gate={gate} "
                f"suggested={suggested} completed={completed} "
                f"busy={busy and busy.get('stage')}"
            )
            if note != last_note:
                print(note, flush=True)
                last_note = note

            if not next_stage and not gate and not busy:
                pub = stages.get("publish") or {}
                if pub.get("status") == "completed" or (
                    pub.get("status") == "awaiting_human" and pub.get("artifact_exists")
                ):
                    if pub.get("status") == "awaiting_human":
                        print("approve final publish gate", flush=True)
                        _approve(c, "publish")
                        time.sleep(2)
                        st = _status_local()
                    print("SUCCESS chain done", flush=True)
                    print(
                        json.dumps(
                            {
                                "completed_stages": st.get("completed_stages"),
                                "next_stage": st.get("next_stage"),
                                "renders": st.get("renders"),
                                "suggested_action": st.get("suggested_action"),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        flush=True,
                    )
                    return 0

            if gate and suggested == "om_state approve" and not busy:
                awaiting = None
                for s in st.get("stages") or []:
                    if s.get("status") == "awaiting_human":
                        awaiting = s["stage"]
                        break
                if awaiting:
                    print(f"auto-approve {awaiting}", flush=True)
                    try:
                        _approve(c, awaiting)
                    except RuntimeError as exc:
                        print("approve error:", exc, flush=True)
                        return 3
                    time.sleep(5)
                    continue

            for s in st.get("stages") or []:
                if s.get("status") == "failed":
                    print("FAIL stage:", s["stage"], flush=True)
                    return 4

            if (
                not busy
                and not gate
                and next_stage
                and st.get("next_runnable_stage") == next_stage
            ):
                print(f"manual kick next={next_stage}", flush=True)
                try:
                    _run(c, next_stage)
                except RuntimeError as exc:
                    print("run error:", exc, flush=True)
                time.sleep(5)
                continue

            time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
