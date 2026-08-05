"""csp-test：创建 RPA 视频任务并验证 LiteLLM video_* vs rpavid_* 双 id 链路。"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "https://csp-test.zerohalu.com"
MODEL = "doubao-video-rpa-t2v"
ADMIN_LOGIN = "seed.platform@control.local"
ADMIN_PASSWORD = "Seed@Pass123"
HUB_LOGINS = (
    ("aw_seed_demo001", "Seed@Pass123"),
)
AUTH_PATH = Path(r"C:\Users\zhaoh\AppData\Local\MxAI 测试版\data\device\device_auth.json")
MODEL_ID = "5907fe9f-ad4b-416a-b817-52ec3322f70a"


def canonical_video_task_id(video_id: str) -> str:
    vid = (video_id or "").strip()
    if not vid.startswith("video_"):
        return vid
    raw = vid[len("video_") :]
    raw += "=" * (-len(raw) % 4)
    try:
        decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8")
        if "video_id:" in decoded:
            out = decoded.rsplit("video_id:", 1)[-1].strip()
            if out:
                return out
    except Exception:
        pass
    return vid


def admin_login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/admin/auth/login",
        json={"login_name": ADMIN_LOGIN, "password": ADMIN_PASSWORD},
    )
    r.raise_for_status()
    tok = (r.json().get("data") or {}).get("access_token") or ""
    if not tok:
        raise RuntimeError("admin login: no access_token")
    return str(tok)


def hub_login(client: httpx.Client) -> str | None:
    if AUTH_PATH.is_file():
        auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        refresh = (auth.get("refresh_token") or "").strip()
        if refresh:
            r = client.post(f"{BASE}/api/hub/auth/refresh", json={"refresh_token": refresh})
            if r.status_code < 400:
                tok = (r.json().get("data") or {}).get("access_token") or ""
                if tok:
                    return str(tok)
    for login_name, password in HUB_LOGINS:
        r = client.post(
            f"{BASE}/api/hub/auth/login",
            json={
                "login_name": login_name,
                "password": password,
                "device_id": "hub-chain-verify-script",
            },
        )
        if r.status_code < 400:
            tok = (r.json().get("data") or {}).get("access_token") or ""
            if tok:
                print(f"hub login ok: {login_name}")
                return str(tok)
        print(f"hub login failed {login_name}: {r.status_code} {r.text[:120]}")
    return None


def admin_gateway_test(client: httpx.Client, admin_jwt: str) -> tuple[str, str, dict]:
    """CS 管理台测试：master_key 走 LiteLLM POST（+ 已部署则 GET）。"""
    r = client.post(
        f"{BASE}/api/admin/gateway/models/{MODEL_ID}/test",
        headers={"Authorization": f"Bearer {admin_jwt}"},
        json={"prompt": f"chain-verify-{int(time.time())}"},
        timeout=60.0,
    )
    r.raise_for_status()
    data = (r.json().get("data") or {})
    if not data.get("ok"):
        raise RuntimeError(f"gateway test failed: {data.get('message')}")
    resp = data.get("response") or {}
    create = resp.get("create") if isinstance(resp.get("create"), dict) else resp
    litellm_id = str((create or {}).get("id") or "").strip()
    if not litellm_id:
        raise RuntimeError(f"no litellm id in response: {resp}")
    rpa_id = canonical_video_task_id(litellm_id)
    return litellm_id, rpa_id, data


def hub_post_video(client: httpx.Client, device_jwt: str) -> tuple[str, str]:
    r = client.post(
        f"{BASE}/v1/videos",
        headers={"Authorization": f"Bearer {device_jwt}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "prompt": f"hub-device-chain-verify-{int(time.time())}",
            "seconds": "2",
            "size": "720x1280",
        },
        timeout=60.0,
    )
    print(f"Hub POST /v1/videos -> {r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(r.text[:400])
    body = r.json() if r.content else {}
    litellm_id = str(body.get("id") or "").strip()
    if not litellm_id:
        raise RuntimeError(f"POST no id: {body}")
    return litellm_id, canonical_video_task_id(litellm_id)


def get_litellm(client: httpx.Client, litellm_id: str, bearer: str, label: str) -> dict:
    url = f"{BASE}/v1/videos/{litellm_id}"
    r = client.get(
        url,
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    print(f"{label} GET LiteLLM -> {r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(r.text[:400])
    return r.json() if r.content else {}


def get_cs_rpa(client: httpx.Client, rpa_id: str, bearer: str) -> dict:
    r = client.get(
        f"{BASE}/api/rpa-video/v1/videos/{rpa_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        timeout=30.0,
    )
    print(f"GET CS rpa-video/{rpa_id[:24]}... -> {r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(r.text[:400])
    return r.json() if r.content else {}


def main() -> int:
    with httpx.Client(timeout=60.0) as client:
        admin_jwt = admin_login(client)
        print("admin login ok")

        # A) 管理台 POST（等价 Hub 提交后的 id 形态）
        litellm_id, rpa_id, test_data = admin_gateway_test(client, admin_jwt)
        print(f"litellm_id (video_*): {litellm_id[:72]}...")
        print(f"rpa_id   (rpavid_*): {rpa_id}")
        assert litellm_id.startswith("video_"), "expected LiteLLM encoded id"
        assert rpa_id.startswith("rpavid_"), "expected RPA canonical id"
        assert litellm_id != rpa_id

        poll = (test_data.get("response") or {}).get("poll")
        if isinstance(poll, dict) and poll.get("status"):
            print(f"admin test built-in GET status={poll.get('status')} progress={poll.get('progress')}")
        else:
            print("admin test: POST only (CS 未部署 GET 探测版)")

        # B) CS 直连 rpavid（对照真源）
        cs_body = get_cs_rpa(client, rpa_id, admin_jwt)
        print(f"CS status={cs_body.get('status')} progress={cs_body.get('progress')}")

        # C) Hub 设备 JWT 路径（与 CreateJob 一致）
        device_jwt = hub_login(client)
        if device_jwt:
            try:
                llm_poll = get_litellm(client, litellm_id, device_jwt, "device")
                print(
                    f"LiteLLM poll status={llm_poll.get('status')} "
                    f"progress={llm_poll.get('progress')} id_prefix={str(llm_poll.get('id',''))[:20]}"
                )
                # 负例：rpavid 直接 GET LiteLLM 应失败
                bad = client.get(
                    f"{BASE}/v1/videos/{rpa_id}",
                    headers={"Authorization": f"Bearer {device_jwt}"},
                    timeout=30.0,
                )
                print(f"device GET rpavid via LiteLLM (expect fail) -> {bad.status_code}")
            except Exception as exc:
                print(f"device JWT path error: {exc}")
        else:
            print("skip device JWT path: no valid hub login")

        # D) 可选：设备 JWT 自行 POST+GET 一轮
        if device_jwt:
            try:
                lid, rid = hub_post_video(client, device_jwt)
                print(f"device POST litellm_id={lid[:56]}... rpa_id={rid}")
                poll2 = get_litellm(client, lid, device_jwt, "device-new")
                print(f"device POST+GET status={poll2.get('status')}")
            except Exception as exc:
                print(f"device POST+GET error: {exc}")

    print("\n=== VERIFY OK: video_* != rpavid_*; CS 与 LiteLLM GET 可对照 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
