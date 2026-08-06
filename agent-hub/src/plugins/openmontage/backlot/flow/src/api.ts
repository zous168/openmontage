// 与 backlot/ui/lib.js 的 getJSON/postJSON/subscribe 等价实现(零构建前端无法跨包 import)

function backlotConfig() {
  const w = window as unknown as {
    __BACKLOT__?: { apiPrefix: string; uiPrefix?: string; mediaPrefix: string };
  };
  return w.__BACKLOT__ || { apiPrefix: "/api", uiPrefix: "", mediaPrefix: "" };
}

function resolveURL(url: string): string {
  const { apiPrefix, mediaPrefix } = backlotConfig();
  if (url.startsWith("/api/")) return apiPrefix + url.slice(4);
  if (url.startsWith("/media/")) return mediaPrefix + "/media/" + url.slice(7);
  if (url.startsWith("/thumb/")) return mediaPrefix + "/thumb/" + url.slice(7);
  return url;
}

/** Page / navigation URLs under the UI mount prefix. */
export function pageURL(path = "/"): string {
  const { uiPrefix } = backlotConfig();
  const p = !path || path === "/" ? "/" : (path.startsWith("/") ? path : `/${path}`);
  if (!uiPrefix) return p;
  if (p === "/") return `${uiPrefix}/`;
  return `${uiPrefix}${p}`;
}

export async function getJSON(url: string): Promise<any> {
  url = resolveURL(url);
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
  url = resolveURL(url);
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
  url = resolveURL(url);
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
  const es = new EventSource(resolveURL(`/api/project/${encodeURIComponent(projectId)}/events`));
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

export { resolveURL };
