import type {VideoProviderOption} from "./videoProviders";
import {ProviderMenu, type ProviderMenuOption} from "./ProviderMenu";

export interface ProviderBarValues {
  preferred_video_provider: string;
  quality_tier: string;
  aspect_ratio: string;
  video_gen_clip_duration_seconds: string;
}

const QUALITY_OPTS = ["720p", "1080p", "4k"] as const;
const ASPECT_OPTS = ["9:16", "16:9", "1:1", "4:5"] as const;
const CLIP_OPTS = ["5", "6", "10", "15"] as const;

interface Props {
  values: ProviderBarValues;
  onChange: (next: ProviderBarValues) => void;
  videoProviders: VideoProviderOption[];
  onSave: () => void;
  busy?: boolean;
}

function menuOpts(items: {value: string; label: string; disabled?: boolean}[]): ProviderMenuOption[] {
  return items;
}

/** 即梦式底部 Provider 条：模型 + 分辨率/时长/比例 + 保存 */
export function ProviderToolbar({values, onChange, videoProviders, onSave, busy}: Props) {
  const set = (patch: Partial<ProviderBarValues>) => onChange({...values, ...patch});

  const providerOptions: ProviderMenuOption[] = [
    {value: "", label: "自动"},
    ...videoProviders
      .filter((o) => o.value !== "auto")
      .map((o) => ({
        value: o.value,
        label: o.label,
        disabled: !o.available,
      })),
  ];

  return (
    <div className="fs-provider-bar">
      <div className="fs-provider-bar-left">
        <span className="fs-provider-icon" aria-hidden title="视频生成">
          ▥
        </span>
        <div className="fs-provider-pill">
          <ProviderMenu
            value={values.preferred_video_provider}
            options={providerOptions}
            placeholder="自动"
            aria-label="视频生成 Provider"
            onChange={(v) => set({preferred_video_provider: v})}
          />
        </div>
        <div className="fs-provider-pill fs-provider-pill--params">
          <ProviderMenu
            compact
            value={values.quality_tier}
            placeholder="画质"
            aria-label="画质"
            options={menuOpts([
              {value: "", label: "画质"},
              ...QUALITY_OPTS.map((q) => ({value: q, label: q})),
            ])}
            onChange={(v) => set({quality_tier: v})}
          />
          <span className="fs-provider-slash">/</span>
          <ProviderMenu
            compact
            value={values.video_gen_clip_duration_seconds}
            placeholder="时长"
            aria-label="单段时长"
            options={menuOpts([
              {value: "", label: "时长"},
              ...CLIP_OPTS.map((s) => ({value: s, label: `${s}s`})),
            ])}
            onChange={(v) => set({video_gen_clip_duration_seconds: v})}
          />
          <span className="fs-provider-slash">/</span>
          <ProviderMenu
            compact
            value={values.aspect_ratio}
            placeholder="比例"
            aria-label="画幅"
            options={menuOpts([
              {value: "", label: "比例"},
              ...ASPECT_OPTS.map((a) => ({value: a, label: a})),
            ])}
            onChange={(v) => set({aspect_ratio: v})}
          />
        </div>
      </div>
      <div className="fs-provider-bar-right">
        <button type="button" className="fs-provider-submit" onClick={onSave} disabled={busy}>
          <span className="fs-provider-submit-label">保存</span>
          <span className="fs-provider-submit-go" aria-hidden>
            ↑
          </span>
        </button>
      </div>
    </div>
  );
}

export function providerBarFromInputs(
  inputs: Record<string, unknown>,
  deliverable?: {quality_tier?: string; aspect_ratio?: string} | null,
): ProviderBarValues {
  return {
    preferred_video_provider:
      inputs.preferred_video_provider != null ? String(inputs.preferred_video_provider) : "",
    quality_tier: String(inputs.quality_tier ?? deliverable?.quality_tier ?? ""),
    aspect_ratio: String(inputs.aspect_ratio ?? deliverable?.aspect_ratio ?? ""),
    video_gen_clip_duration_seconds:
      inputs.video_gen_clip_duration_seconds != null
        ? String(inputs.video_gen_clip_duration_seconds)
        : "",
  };
}

export function providerBarPatch(
  values: ProviderBarValues,
  existing: Record<string, unknown>,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  const vp = values.preferred_video_provider.trim();
  if (vp) patch.preferred_video_provider = vp;
  else if (existing.preferred_video_provider) patch.preferred_video_provider = null;

  const qt = values.quality_tier.trim();
  if (qt) patch.quality_tier = qt;
  else if (existing.quality_tier) patch.quality_tier = null;

  const ar = values.aspect_ratio.trim();
  if (ar) patch.aspect_ratio = ar;
  else if (existing.aspect_ratio) patch.aspect_ratio = null;

  const clip = values.video_gen_clip_duration_seconds.trim();
  if (clip) patch.video_gen_clip_duration_seconds = Number(clip);
  else if (existing.video_gen_clip_duration_seconds != null) patch.video_gen_clip_duration_seconds = null;

  return patch;
}
