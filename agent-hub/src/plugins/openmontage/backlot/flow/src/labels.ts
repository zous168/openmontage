// 双语表子集 — 照 backlot/ui/i18n.js 的 STAGE_NAMES / ARTIFACT_NAMES / STATUS_LABELS

export const STAGE_NAMES: Record<string, string> = {
  research: "调研",
  proposal: "方案",
  idea: "创意",
  script: "脚本",
  scene_plan: "分镜",
  assets: "资产",
  edit: "剪辑",
  compose: "合成",
  publish: "发布",
  character_design: "角色设计",
  rig_plan: "绑骨方案",
  reference: "参考分析",
  reference_analysis: "参考分析",
  source_media_review: "源素材审阅",
  sample: "样片预览",
  scene: "分镜",
};

export const ARTIFACT_NAMES: Record<string, string> = {
  research_brief: "调研简报",
  proposal_packet: "制作方案",
  brief: "创意简报",
  script: "脚本",
  scene_plan: "分镜计划",
  asset_manifest: "资产清单",
  edit_decisions: "剪辑决策",
  render_report: "渲染报告",
  final_review: "终检",
  publish_log: "发布计划",
  decision_log: "决策日志",
  video_analysis_brief: "视频分析简报",
  source_media_review: "源素材审阅",
  character_design: "角色设计",
  rig_plan: "绑骨方案",
  pose_library: "姿势库",
};

export const STATUS_LABELS: Record<string, string> = {
  completed: "已完成",
  in_progress: "进行中",
  awaiting_human: "待审批",
  failed: "失败",
  pending: "待开始",
  pendingNext: "待运行",
  unknown: "未知",
};

export const STRINGS = {
  stalledRail: "可能卡住",
  stalledDetail: (n: number) => `⚠ 可能卡住 ${n} 分钟`,
  blockedByUpstreamHint: "等待上游",
  approvedSuffix: " · 已批准",
  inProgress: "进行中",
  scenesDone: (n: number) => `${n} 个场景完成`,
  awaitingApprovalHint: "点击节点 · 批准或驳回",
  awaitingApproveFirst: "请先批准本阶段，批准后将自动进入下一阶段",
  gateSkipped: "跳过门",
  undeclared: "未声明",
  unlisted: "未列出",
  running: "运行中",
  awaitingYou: "◈ 待你确认",
  nextStage: "下一阶段",
  resetChip: "已重置",
  revisionChip: (n: number) => `v${n} 重跑`,
  noState: "流水线尚未启动",
  back: "返回",
  switchToBoard: "切换到 Board",
  switchToFlow: "流程图",
  openBoard: "打开看板",
  runStage: "运行此阶段",
  approve: "批准",
  reject: "驳回",
  cancelRun: "取消运行",
  runLog: "运行日志",
  resetPipeline: "重置流水线",
  resetConfirm: "确认重置整个流水线?已完成的阶段将回到待开始。",
  outputs: (n: number) => `产出 ${n}`,
  history: "阶段历史",
  artifacts: "产物",
  meta: "元信息",
  retry: "重试",
  failureReason: "失败原因",
  viewRunLog: "查看运行日志",
  viewFailureDetails: "查看失败详情",
  unknownFailure: "未知错误（请查看运行日志）",
  loadFailed: "加载项目状态失败",
  loadingProject: "正在加载项目…",
  projectNotFound: "项目不存在",
  fitView: "适应视图",
} as const;

export function stageLabel(name: string): string {
  return STAGE_NAMES[name] ?? name;
}

export function artifactLabel(name: string): string {
  return ARTIFACT_NAMES[name] ?? name;
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? STATUS_LABELS.unknown;
}

/** 与 board.js railStatusLabel 对齐 */
export function railStatusLabel(st: {
  status?: string;
  stalled?: boolean;
  is_next?: boolean;
  active_run_id?: string | null;
  superseded_by_downstream?: boolean;
  versions?: number;
}): string {
  if (st.status === "in_progress") return statusLabel("in_progress");
  if (st.stalled) return STRINGS.stalledRail;
  if (st.superseded_by_downstream) {
    return (st.versions ?? 0) > 1 ? "已重置" : "已跳过";
  }
  if (st.is_next && (st.status === "pending" || !st.status)) return statusLabel("pendingNext");
  return statusLabel(st.status || "pending");
}
