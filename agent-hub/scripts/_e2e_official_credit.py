"""本机官方渠道 E2E：设备 JWT → 网关 chat → Redis / ledger。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH_PATH = ROOT / ".data" / "device" / "device_auth.json"


def _http_json(method: str, url: str, *, token: str | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail[:1500]}") from e


def main() -> int:
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    token = auth["access_token"]
    tenant_id = auth["tenant_id"]
    print(f"1) device ok tenant={tenant_id} credit_balance={auth.get('credit_balance')}")

    r = None
    key = f"credit:balance:{tenant_id}"
    try:
        import redis

        r = redis.Redis.from_url("redis://srv.zerohalu.com:8379/2", decode_responses=True)
        print(f"2) redis before {key}={r.get(key)}")
    except Exception as e:
        print(f"2) redis skip: {e}")

    print("3) gateway chat ...")
    chat = _http_json(
        "POST",
        "http://127.0.0.1:4000/v1/chat/completions",
        token=token,
        body={
            "model": "MiniMax-M2.7",
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 16,
        },
    )
    content = chat["choices"][0]["message"]["content"]
    print(f"   content={content!r} usage={chat.get('usage')}")

    time.sleep(4)
    if r is not None:
        print(f"4) redis after {key}={r.get(key)}")

    admin = _http_json(
        "POST",
        "http://127.0.0.1:3000/api/admin/auth/login",
        body={
            "login_name": "seed.platform@control.local",
            "password": "Seed@Pass123",
        },
    )
    data = admin.get("data") or admin
    admin_token = (
        data.get("access_token")
        or (data.get("tokens") or {}).get("access_token")
        or admin.get("access_token")
    )
    if not admin_token:
        print(f"5) admin login unexpected: {list(admin.keys())} data={list(data.keys()) if isinstance(data, dict) else data}")
        return 3
    print("5) admin login ok")

    ledger = _http_json(
        "GET",
        f"http://127.0.0.1:3000/api/admin/credit/ledger?page=1&page_size=5&source_type=consume&tenant_id={tenant_id}",
        token=admin_token,
    )
    ldata = ledger.get("data") or ledger
    items = ldata.get("items") or []
    print(f"6) ledger total={ldata.get('total')} latest={json.dumps(items[:2], ensure_ascii=False)[:900]}")

    sys.path.insert(0, str(ROOT / "agent-hub" / "src"))
    os.environ.setdefault("HUB_DATA_DIR", str(ROOT / ".data"))
    from agent.account_usage import build_credits_view

    view = build_credits_view(markdown=True)
    print(
        f"7) /credits source={view.source} logged_in={view.logged_in} "
        f"lines={view.balance_lines}"
    )
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
