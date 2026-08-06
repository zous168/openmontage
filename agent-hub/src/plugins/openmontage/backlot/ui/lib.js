// Shared helpers for the Backlot UI.

export { fmtAgo } from "/ui/i18n.js";

function backlotConfig() {
  if (window.__BACKLOT__) return window.__BACKLOT__;
  // Hub pages live under /plugins/openmontage — derive prefixes if inject missed.
  const onHub = location.pathname.startsWith("/plugins/openmontage");
  return {
    apiPrefix: onHub ? "/api/plugins/openmontage" : "/api",
    uiPrefix: onHub ? "/plugins/openmontage" : "",
    mediaPrefix: onHub ? "/api/plugins/openmontage" : "",
  };
}

/** Rewrite root absolute Backlot URLs to the mounted namespace. */
export function resolveURL(url) {
  if (!url || typeof url !== "string") return url;
  if (/^https?:\/\//i.test(url) || url.startsWith("//")) return url;
  const { apiPrefix, mediaPrefix } = backlotConfig();
  if (url.startsWith("/api/")) return apiPrefix + url.slice(4); // "/api/foo" -> "{apiPrefix}/foo"
  if (url.startsWith("/media/")) return mediaPrefix + "/media/" + url.slice(7);
  if (url.startsWith("/thumb/")) return mediaPrefix + "/thumb/" + url.slice(7);
  return url;
}

/** Page / navigation URLs under the UI mount prefix (hub: /plugins/openmontage). */
export function pageURL(path = "/") {
  const { uiPrefix } = backlotConfig();
  const p = !path || path === "/" ? "/" : (path.startsWith("/") ? path : `/${path}`);
  if (!uiPrefix) return p;
  if (p === "/") return `${uiPrefix}/`;
  return `${uiPrefix}${p}`;
}

function handleAuth(res) {
  if (res.status === 401) {
    // Hub login page
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
    throw new Error("unauthorized");
  }
}

export async function getJSON(url) {
  url = resolveURL(url);
  const res = await fetch(url);
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" && detail ? detail : `${res.status} ${url}`);
  }
  return data;
}

export async function deleteJSON(url) {
  url = resolveURL(url);
  const res = await fetch(url, { method: "DELETE" });
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg = `${res.status} ${url}`;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export async function postForm(url, formData) {
  url = resolveURL(url);
  const res = await fetch(url, { method: "POST", body: formData });
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg = `${res.status} ${url}`;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export async function postJSON(url, body) {
  url = resolveURL(url);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg = `${res.status} ${url}`;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export async function putJSON(url, body) {
  url = resolveURL(url);
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg = `${res.status} ${url}`;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export async function patchJSON(url, body) {
  url = resolveURL(url);
  const res = await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  handleAuth(res);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data?.detail;
    let msg = `${res.status} ${url}`;
    if (typeof detail === "string" && detail) msg = detail;
    else if (Array.isArray(detail)) msg = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    else if (detail && typeof detail === "object") msg = JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children.flat()) {
    if (child == null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function fmtDuration(seconds) {
  const n = Number(seconds);
  if (seconds == null || !Number.isFinite(n)) return "";
  const s = Math.max(0, Math.round(n));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function fmtMoney(v) {
  const n = Number(v);
  if (v == null || !Number.isFinite(n)) return "—";
  return `$${n.toFixed(2)}`;
}

export function fmtClock(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

export function mediaURL(projectId, relPath) {
  const { mediaPrefix } = backlotConfig();
  const path = `${encodeURIComponent(projectId)}/${relPath.split("/").map(encodeURIComponent).join("/")}`;
  return `${mediaPrefix}/media/${path}`;
}

/** Detach hero <video> nodes before a full board re-render so SSE/replay ticks
 *  do not reload the same src (which flashes the render-hero frame). */
const pinnedMedia = new Map();

export function pinMediaElements(selectors = [".render-hero video", ".source-hero video"]) {
  for (const sel of selectors) {
    for (const node of document.querySelectorAll(sel)) {
      const src = node.getAttribute("src");
      if (!src) continue;
      node.remove();
      pinnedMedia.set(src, node);
    }
  }
}

export function takePinnedMedia(src) {
  const node = pinnedMedia.get(src);
  if (node) pinnedMedia.delete(src);
  return node || null;
}

export function releaseUnusedPinnedMedia() {
  pinnedMedia.clear();
}

// Downscaled cached JPEG for images (full media only in players/lightbox).
export function thumbURL(projectId, relPath, w = 640) {
  const { mediaPrefix } = backlotConfig();
  const path = `${encodeURIComponent(projectId)}/${relPath.split("/").map(encodeURIComponent).join("/")}`;
  return `${mediaPrefix}/thumb/${path}?w=${w}`;
}

// Subscribe to a server-sent change feed; call onChange (debounced) per burst.
export function subscribe(url, onChange) {
  url = resolveURL(url);
  let timer = null;
  const source = new EventSource(url);
  source.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type !== "change") return;
    } catch {
      return;
    }
    clearTimeout(timer);
    timer = setTimeout(onChange, 250);
  };
  source.onerror = () => { /* EventSource auto-reconnects */ };
  return source;
}

// Deterministic pseudo-waveform bars (seeded by a string).
export function waveBars(container, seedStr, count = 26, maxH = 14) {
  let seed = 0;
  for (const c of seedStr || "wave") seed = (seed * 31 + c.charCodeAt(0)) % 2147483647;
  seed = seed || 7;
  container.innerHTML = "";
  for (let i = 0; i < count; i++) {
    seed = (seed * 16807) % 2147483647;
    const h = 3 + ((seed % 100) / 100) * maxH * (0.55 + 0.45 * Math.sin(i / 5));
    const bar = document.createElement("i");
    bar.style.height = `${Math.max(3, h)}px`;
    container.append(bar);
  }
}

export function brandMark({ size = 40, hidden = false } = {}) {
  const { uiPrefix } = backlotConfig();
  const brand = (name) => `${uiPrefix}/brand/${name}`;
  const wrap = el("div", {
    class: "brand-mark-wrap",
    "aria-hidden": hidden ? "true" : null,
    style: `--brand-mark-size: ${size}px`,
  });
  const imgAttrs = {
    class: "brand-mark",
    width: String(size),
    height: String(size),
    alt: "Monty the Clapper",
    decoding: "async",
  };
  wrap.append(
    el("img", { ...imgAttrs, class: "brand-mark brand-mark-dark", src: brand("monty-dark.svg") }),
    el("img", { ...imgAttrs, class: "brand-mark brand-mark-light", src: brand("monty-light.svg") }),
  );
  return wrap;
}


export const STAGE_ICONS = {
  completed: "✓",
  in_progress: "◉",
  awaiting_human: "◈",
  failed: "✕",
};
