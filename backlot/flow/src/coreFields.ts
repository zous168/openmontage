// 阶段核心信息字段表 — 驱动 StageDrawer 的表单渲染与 parameters 组装。
// artifactPath: 从 state.artifacts[<canonical artifact>] 预填值的路径。
// decision: 保存时写入 decision_log 的 (category, subject),category 必须
// 是 decision_log schema 的闭枚举值。

export interface CoreField {
  key: string;              // 写入 parameters 的设置键
  label: string;            // 中文标签
  type: "select" | "number" | "text";
  options?: string[];       // select 选项
  dynamicOptions?: "video_providers"; // 运行时从 API 拉取
  artifactPath: string[];   // 在 canonical artifact 里的取值路径(空 = 无预填)
  productionInputKey?: string; // 从 meta.production_inputs 预填
  decision: {category: string; subject: string};
}

export const RENDER_RUNTIMES = ["remotion", "hyperframes", "ffmpeg"];
export const COMPOSITION_MODES = ["templated", "atelier"];

export const CORE_FIELDS: Record<string, CoreField[]> = {
  proposal: [
    {
      key: "render_runtime",
      label: "渲染引擎",
      type: "select",
      options: RENDER_RUNTIMES,
      artifactPath: ["proposal_packet", "production_plan", "render_runtime"],
      decision: {category: "render_runtime_selection", subject: "合成方案(render_runtime)"},
    },
    {
      key: "renderer_family",
      label: "渲染族",
      type: "select",
      options: ["explainer-data", "explainer-teacher", "cinematic-trailer", "documentary-montage", "product-reveal", "screen-demo", "presenter", "animation-first"],
      artifactPath: ["proposal_packet", "production_plan", "renderer_family"],
      decision: {category: "renderer_family_selection", subject: "渲染族(renderer_family)"},
    },
    {
      key: "playbook",
      label: "风格画册",
      type: "select",
      options: ["clean-professional", "premium-minimalist", "flat-motion-graphics", "minimalist-diagram", "ink-sketch"],
      artifactPath: ["proposal_packet", "production_plan", "playbook"],
      decision: {category: "playbook_selection", subject: "风格画册(playbook)"},
    },
    {
      key: "budget_cap_usd",
      label: "预算上限($)",
      type: "number",
      artifactPath: ["proposal_packet", "cost_estimate", "budget_cap_usd"],
      decision: {category: "budget_tradeoff", subject: "预算上限(budget_cap_usd)"},
    },
    {
      key: "preferred_video_provider",
      label: "视频生成 Provider",
      type: "select",
      options: ["auto"],
      dynamicOptions: "video_providers",
      artifactPath: [],
      productionInputKey: "preferred_video_provider",
      decision: {category: "provider_selection", subject: "视频生成 Provider(preferred_video_provider)"},
    },
  ],
  scene_plan: [
    {
      key: "style_playbook",
      label: "风格画册",
      type: "select",
      options: ["clean-professional", "premium-minimalist", "flat-motion-graphics", "minimalist-diagram", "ink-sketch"],
      artifactPath: ["scene_plan", "style_playbook"],
      decision: {category: "playbook_override", subject: "分镜风格画册(style_playbook)"},
    },
  ],
  edit: [
    {
      key: "render_runtime",
      label: "渲染引擎",
      type: "select",
      options: RENDER_RUNTIMES,
      artifactPath: ["edit_decisions", "render_runtime"],
      decision: {category: "render_runtime_selection", subject: "合成方案(render_runtime)"},
    },
    {
      key: "composition_mode",
      label: "合成模式",
      type: "select",
      options: COMPOSITION_MODES,
      artifactPath: ["edit_decisions", "composition_mode"],
      decision: {category: "composition_mode", subject: "合成模式(composition_mode)"},
    },
  ],
  assets: [
    {
      key: "preferred_video_provider",
      label: "视频生成 Provider",
      type: "select",
      options: ["auto"],
      dynamicOptions: "video_providers",
      artifactPath: [],
      productionInputKey: "preferred_video_provider",
      decision: {category: "provider_selection", subject: "视频生成 Provider(preferred_video_provider)"},
    },
    {
      key: "budget_cap_usd",
      label: "预算上限($)",
      type: "number",
      artifactPath: ["asset_manifest", "total_cost_usd"],
      decision: {category: "budget_tradeoff", subject: "资产预算(budget_cap_usd)"},
    },
  ],
};

// 只读摘要:无编辑字段的阶段也可展示的关键值(artifactPath 提取)
export const READONLY_SUMMARY: Record<string, {label: string; path: string[]}[]> = {
  script: [
    {label: "总时长(秒)", path: ["script", "total_duration_seconds"]},
    {label: "段落数", path: ["script", "sections"]},
  ],
  scene_plan: [
    {label: "场景数", path: ["scene_plan", "scenes"]},
    {label: "总时长(秒)", path: ["scene_plan", "scenes"]},
  ],
  assets: [
    {label: "资产总数", path: ["asset_manifest", "assets"]},
    {label: "总成本($)", path: ["asset_manifest", "total_cost_usd"]},
  ],
  compose: [
    {label: "输出", path: ["render_report", "outputs"]},
    {label: "渲染耗时(秒)", path: ["render_report", "render_time_seconds"]},
  ],
};

export function getCoreFields(stageName: string): CoreField[] {
  return CORE_FIELDS[stageName] ?? [];
}
