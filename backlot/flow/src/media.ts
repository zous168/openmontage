// 媒体 URL 工具 — 接收产物里的媒体路径(path),生成缩略图/媒体 URL。
// 展示层从产物(artifacts)推导媒体卡,前端零阶段知识。

const VIDEO_EXT = [".mp4", ".webm", ".mov"];
const IMAGE_EXT = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"];
const AUDIO_EXT = [".mp3", ".wav", ".m4a", ".ogg"];

export function normPath(path: string, projectId: string): string {
  const clean = String(path ?? "").replace(/\\/g, "/");
  const prefix = `projects/${projectId}/`;
  const idx = clean.indexOf(prefix);
  const rel = idx >= 0 ? clean.slice(idx + prefix.length) : clean;
  return rel.replace(/^\.?\//, "");
}

function encodeSegments(projectId: string, path: string): string {
  return normPath(path, projectId)
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

export function thumbURL(projectId: string, path: string, w = 320): string {
  return `/thumb/${encodeURIComponent(projectId)}/${encodeSegments(projectId, path)}?w=${w}`;
}

export function mediaURL(projectId: string, path: string): string {
  return `/media/${encodeURIComponent(projectId)}/${encodeSegments(projectId, path)}`;
}

export function kindOfPath(path: string): "video" | "image" | "audio" | "text" {
  const lower = String(path ?? "").toLowerCase();
  if (VIDEO_EXT.some((e) => lower.endsWith(e))) return "video";
  if (IMAGE_EXT.some((e) => lower.endsWith(e))) return "image";
  if (AUDIO_EXT.some((e) => lower.endsWith(e))) return "audio";
  return "text";
}
