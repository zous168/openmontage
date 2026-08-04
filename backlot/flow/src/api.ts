// 与 backlot/ui/lib.js 的 getJSON/postJSON/subscribe 等价实现(零构建前端无法跨包 import)

export async function getJSON(url: string): Promise<any> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function patchJSON(url: string, body?: unknown): Promise<any> {
  const res = await fetch(url, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = String(b.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function postJSON(url: string, body?: unknown): Promise<any> {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = String(b.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

// SSE 订阅:type==="change" 事件 → 250ms 防抖回调(照 lib.js subscribe)
export function subscribeSSE(projectId: string, onChange: () => void): EventSource {
  const es = new EventSource(`/api/project/${encodeURIComponent(projectId)}/events`);
  let timer: ReturnType<typeof setTimeout> | null = null;
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data?.type !== "change") return;
    } catch {
      return;
    }
    if (timer) clearTimeout(timer);
    timer = setTimeout(onChange, 250);
  };
  return es;
}
