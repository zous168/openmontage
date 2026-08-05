"""CR-131 实例烟测：对运行中的 Hub :8642 调用 pending-add API."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8642"
MXAI = f"{BASE}/api/plugins/mxai"


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    hdrs = dict(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def main() -> int:
    login_body = {"login_name": "aw_seed_demo001", "password": "Seed@Pass123"}
    code, _ = http("POST", f"{BASE}/api/auth/login", login_body)
    if code != 200:
        print(f"FAIL login ({code})")
        return 1

    code, ipc = http("GET", f"{BASE}/api/auth/dev/local-ipc-token")
    if code != 200 or not ipc.get("token"):
        print(f"FAIL ipc token ({code})")
        return 1

    H = {"X-Hub-Local-Token": ipc["token"]}
    results: list[tuple[str, bool]] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok))
        mark = "PASS" if ok else "FAIL"
        line = f"  {mark}: {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    ts = int(time.time())
    c1, c2 = f"e2e_{ts}_a", f"e2e_{ts}_b"

    code, lst = http("GET", f"{MXAI}/agents/wechat/pending-add-contacts", headers=H)
    step("GET pending list", code == 200, f"total={lst.get('total', '?')}")

    code, imp = http(
        "POST",
        f"{MXAI}/agents/wechat/pending-add-contacts/import",
        {"text": f"{c1}\n{c2}"},
        headers=H,
    )
    step("POST import paste", code == 200 and imp.get("added") == 2, f"added={imp.get('added')}")

    code, lst2 = http("GET", f"{MXAI}/agents/wechat/pending-add-contacts", headers=H)
    ids = {i["contact_id"] for i in lst2.get("items", [])}
    step("list contains new rows", c1 in ids and c2 in ids)

    code, dup = http(
        "POST",
        f"{MXAI}/agents/wechat/pending-add-contacts/import",
        {"text": c1},
        headers=H,
    )
    dup_code = dup.get("detail", {}).get("code") if isinstance(dup.get("detail"), dict) else None
    step("duplicate returns 409", code == 409 and dup_code == "duplicates")

    pid = next(i["pending_id"] for i in lst2["items"] if i["contact_id"] == c1)
    code, _ = http("DELETE", f"{MXAI}/agents/wechat/pending-add-contacts/{pid}", headers=H)
    step("DELETE pending row", code == 200)

    code, wl = http(
        "GET",
        f"{MXAI}/agents/wechat/worklogs?limit=5&op_type=add_friends",
        headers=H,
    )
    ok_wl = code == 200 and all(i.get("op_type") == "add_friends" for i in wl.get("items", []))
    step("worklogs op_type filter", ok_wl, f"count={wl.get('total', 0)}")

    code, enq = http(
        "POST",
        f"{MXAI}/agents/wechat/pending-add-contacts/enqueue",
        {"all_pending": True, "mode": "all"},
        headers=H,
    )
    if code == 200:
        step("enqueue", True, f"queued={enq.get('queued')}")
    elif code == 409:
        detail = enq.get("detail")
        if isinstance(detail, dict) and detail.get("code") == "limit_exceeded":
            step("enqueue limit modal path", True, f"remaining={detail.get('remaining')}")
        else:
            step("enqueue (work not started)", True, str(detail)[:80])
    elif code == 429:
        step("enqueue risk blocked", True, str(enq.get("detail"))[:80])
    else:
        step("enqueue", False, str(enq)[:120])

    # cleanup e2e rows
    code, lst3 = http("GET", f"{MXAI}/agents/wechat/pending-add-contacts", headers=H)
    for row in lst3.get("items", []):
        if str(row.get("contact_id", "")).startswith("e2e_"):
            http("DELETE", f"{MXAI}/agents/wechat/pending-add-contacts/{row['pending_id']}", headers=H)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print("---")
    print(f"E2E instance test: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
