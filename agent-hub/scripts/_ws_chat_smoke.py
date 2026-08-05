"""Smoke-test in-process /api/ws chat (default profile gateway attach path)."""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import websockets

BASE = "http://127.0.0.1:8642"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        login = await client.post(
            "/api/auth/login",
            json={"login_name": "ai_worker", "password": "dev"},
        )
        login.raise_for_status()
        ipc = await client.get("/api/auth/dev/local-ipc-token")
        ipc.raise_for_status()
        ipc_token = ipc.json()["token"]
        headers = {"X-Hub-Local-Token": ipc_token}
        ticket_resp = await client.post("/api/auth/ws-ticket", headers=headers)
        ticket_resp.raise_for_status()
        ticket = ticket_resp.json()["ticket"]
        status = await client.get("/api/status", headers=headers)
        status.raise_for_status()
        st = status.json()
        print("gateway_running:", st.get("gateway_running"), "pid:", st.get("gateway_pid"))
        print("auth_required:", st.get("auth_required"))

    # In integrated (hub_ipc) mode the WS handler's _ws_auth_reason first
    # checks for the local_ipc_token COOKIE (extract_ipc_from_ws_headers),
    # then ?internal=, and skips the ?ticket= branch entirely.  The browser
    # sends the cookie automatically; we must include it explicitly here.
    ws_url = f"ws://127.0.0.1:8642/api/ws"
    async with websockets.connect(
        ws_url,
        open_timeout=15,
        close_timeout=5,
        additional_headers={
            "X-Hub-Local-Token": ipc_token,
            "Cookie": f"local_ipc_token={ipc_token}",
        },
    ) as ws:
        ready_raw = await asyncio.wait_for(ws.recv(), timeout=15)
        ready = json.loads(ready_raw)
        params = ready.get("params") or {}
        if ready.get("method") != "event" or params.get("type") != "gateway.ready":
            print("unexpected first frame:", ready_raw[:200])
            return 1
        print("gateway.ready OK")

        await ws.send(
            json.dumps(
                {"jsonrpc": "2.0", "id": "t1", "method": "session.create", "params": {}}
            )
        )
        create = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        if create.get("error"):
            print("session.create error:", create["error"])
            return 1
        sid = (create.get("result") or {}).get("session_id")
        if not sid:
            print("no session_id:", create)
            return 1
        print("session.create OK sid=", sid)

        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "t2",
                    "method": "prompt.submit",
                    "params": {"session_id": sid, "text": "ping"},
                }
            )
        )
        deadline = time.time() + 45
        events: list[str] = []
        got_delta = False
        got_complete = False
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if msg.get("id") == "t2":
                if msg.get("error"):
                    print("prompt.submit error:", msg["error"])
                    return 1
                print("prompt.submit accepted")
                continue
            if msg.get("method") != "event":
                continue
            ev = msg.get("params") or {}
            t = ev.get("type")
            if t in ("message.delta", "message.complete", "error", "status.update"):
                events.append(str(t))
            if t == "message.delta":
                got_delta = True
            if t == "message.complete":
                got_complete = True
                break
            if t == "error":
                print("agent error event:", ev)
                return 1

        print("events:", events)
        if not got_complete and not got_delta:
            print("FAIL: no message.delta/complete within 45s")
            return 1
        print("chat E2E OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
