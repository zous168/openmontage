import {getJSON} from "./api";
import {videoProviderLabel} from "./fieldLabels";

export interface VideoProviderOption {
  value: string;
  label: string;
  available: boolean;
  toolName?: string;
}

/** 从 system check 拉取 video_generation 能力下的 provider 列表 */
export async function fetchVideoProviderOptions(): Promise<VideoProviderOption[]> {
  const data = await getJSON("/api/system/dependencies?check=true");
  const menu = (data.provider_menu ?? {}) as Record<
    string,
    {available?: {provider?: string; name?: string}[]; unavailable?: {provider?: string; name?: string}[]}
  >;
  const bucket = menu.video_generation;
  if (!bucket) {
    return [{value: "auto", label: videoProviderLabel("auto"), available: true}];
  }

  const byProvider = new Map<string, VideoProviderOption>();

  for (const entry of bucket.available ?? []) {
    const p = entry.provider;
    if (!p) continue;
    byProvider.set(p, {
      value: p,
      label: videoProviderLabel(p, entry.name),
      available: true,
      toolName: entry.name,
    });
  }
  for (const entry of bucket.unavailable ?? []) {
    const p = entry.provider;
    if (!p || byProvider.has(p)) continue;
    byProvider.set(p, {
      value: p,
      label: `${videoProviderLabel(p, entry.name)}（未配置）`,
      available: false,
      toolName: entry.name,
    });
  }

  const sorted = [...byProvider.values()].sort((a, b) => a.label.localeCompare(b.label, "zh"));
  return [{value: "auto", label: videoProviderLabel("auto"), available: true}, ...sorted];
}

/** decision_log 审计用：列出 provider 选项 id（含 auto 与当前选中） */
export function providerOptionsForDecision(
  providers: VideoProviderOption[],
  selected: string,
  max = 64,
): string[] {
  const picked = (selected || "auto").trim() || "auto";
  const out: string[] = ["auto"];
  if (picked !== "auto") out.push(picked);
  for (const o of providers) {
    if (out.length >= max) break;
    if (!out.includes(o.value)) out.push(o.value);
  }
  return out;
}
