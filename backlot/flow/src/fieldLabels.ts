/** 核心设置字段选项的中文显示（value 仍为英文 id，提交不变） */

export const RENDER_RUNTIME_LABELS: Record<string, string> = {
  remotion: "Remotion（React 合成）",
  hyperframes: "HyperFrames（网页动效）",
  ffmpeg: "FFmpeg（纯剪辑）",
};

export const RENDERER_FAMILY_LABELS: Record<string, string> = {
  "explainer-data": "解说 · 数据可视化",
  "explainer-teacher": "解说 · 教师讲解",
  "cinematic-trailer": "电影感预告",
  "documentary-montage": "纪录片蒙太奇",
  "product-reveal": "产品发布",
  "screen-demo": "屏幕演示",
  "presenter": "出镜主持",
  "animation-first": "动画优先",
};

export const COMPOSITION_MODE_LABELS: Record<string, string> = {
  templated: "模板装配",
  atelier: "定制手工",
};

/** video_selector.preferred_provider 常用 provider id → 中文 */
export const VIDEO_PROVIDER_LABELS: Record<string, string> = {
  auto: "自动（按评分选择）",
  seedance: "Seedance 2.0",
  kling: "Kling",
  kling_official: "Kling 官方",
  veo: "Google Veo",
  gemini_omni: "Gemini 视频",
  grok: "Grok 视频",
  volcengine: "即梦 / 火山",
  higgsfield: "Higgsfield",
  openai: "Sora / OpenAI",
  runway: "Runway",
  minimax: "MiniMax",
  heygen: "HeyGen 路由",
  ltx: "LTX 本地",
  "ltx-modal": "LTX Modal",
  wan: "Wan 本地",
  cogvideo: "CogVideo 本地",
};

export function videoProviderLabel(provider: string, toolName?: string): string {
  if (!provider) return "（未设置）";
  if (provider === "auto") return VIDEO_PROVIDER_LABELS.auto;
  const base = VIDEO_PROVIDER_LABELS[provider] ?? provider;
  if (toolName && !base.includes(toolName)) return `${base} · ${toolName}`;
  return base;
}

/** API 未返回时的风格画册兜底（与 styles/*.yaml name_zh 对齐） */
export const PLAYBOOK_FALLBACK: Record<string, string> = {
  "clean-professional": "干净专业",
  "premium-minimalist": "高级极简",
  "flat-motion-graphics": "扁平动效",
  "minimalist-diagram": "极简图解",
  "ink-sketch": "墨水素描",
  "anime-ghibli": "吉卜力动画",
};

export function playbookLabel(value: string, fromApi?: Record<string, string>): string {
  if (!value) return "（未设置）";
  return fromApi?.[value] ?? PLAYBOOK_FALLBACK[value] ?? value;
}

export function optionLabel(
  fieldKey: string,
  value: string,
  playbookLabels?: Record<string, string>,
): string {
  if (!value) return "（未设置）";
  switch (fieldKey) {
    case "playbook":
    case "style_playbook":
      return playbookLabel(value, playbookLabels);
    case "render_runtime":
      return RENDER_RUNTIME_LABELS[value] ?? value;
    case "renderer_family":
      return RENDERER_FAMILY_LABELS[value] ?? value;
    case "composition_mode":
      return COMPOSITION_MODE_LABELS[value] ?? value;
    case "preferred_video_provider":
      return videoProviderLabel(value);
    default:
      return value;
  }
}
