/**
 * Flow 连线视觉规范（唯一真相源）
 *
 * | 线型   | 颜色 | 动画     | 含义 |
 * |--------|------|----------|------|
 * | 实线   | 绿   | 无       | 已走过：上游已完成，产物已沿此边传递 |
 * | 实线   | 蓝   | 光点流动 | 进行中：连入 in_progress 节点（入口）；或「已完成→待运行下一阶段」 |
 * | 实线   | 蓝   | 无       | 可能卡住：in_progress 节点 stalled |
 * | 实线   | 琥珀 | 无       | 待审批：连入 awaiting_human 节点 |
 * | 虚线   | 灰   | 无       | 未接通：含「运行节点出口→未开始下游」（下游还没轮到） |
 * | 虚线   | 红   | 无       | 失败：连入 failed 节点 |
 *
 * 顺序边 prev → next：
 * - prev 进行中 & next 未开始 → 灰虚线（运行节点后面保持未接通）
 * - next 进行中 → 蓝实线 + 光点（连入运行节点）
 *
 * 输入节点 → 首阶段：与「连入首阶段」规则一致（首阶段 in_progress = 蓝实线+光点）。
 */
import type {StageState} from "./types";

export type EdgeVariant = "done" | "active" | "await" | "failed" | "pending";
export type EdgeLineStyle = "solid" | "dashed";

export interface ResolvedEdgeStyle {
  variant: EdgeVariant;
  lineStyle: EdgeLineStyle;
  /** 实线上的流动光点（仅 active 且未 stalled） */
  flowing: boolean;
  className: string;
}

function edgeClassName(variant: EdgeVariant): string {
  if (variant === "done") return "edge-done";
  if (variant === "active") return "edge-active";
  if (variant === "failed") return "edge-failed";
  if (variant === "await") return "edge-await";
  return "edge-pending";
}

function resolve(
  variant: EdgeVariant,
  flowing: boolean,
): ResolvedEdgeStyle {
  const lineStyle: EdgeLineStyle =
    variant === "pending" || variant === "failed" ? "dashed" : "solid";
  return {
    variant,
    lineStyle,
    flowing: flowing && variant === "active" && lineStyle === "solid",
    className: edgeClassName(variant),
  };
}

/** 输入节点 → 流水线首阶段 */
export function resolveInputEdge(first: StageState): ResolvedEdgeStyle {
  if (first.status === "completed") return resolve("done", false);
  if (first.status === "in_progress") return resolve("active", !first.stalled);
  if (first.status === "awaiting_human") return resolve("await", false);
  if (first.status === "failed") return resolve("failed", false);
  if (first.is_next) return resolve("active", true);
  return resolve("pending", false);
}

/** 顺序边：上游 prev → 下游 next */
export function resolveStageEdge(prev: StageState, next: StageState): ResolvedEdgeStyle {
  if (prev.status === "failed") return resolve("pending", false);
  if (next.status === "failed") return resolve("failed", false);
  if (prev.status === "awaiting_human") return resolve("pending", false);
  if (next.blocked_by_upstream) return resolve("pending", false);
  // 运行节点出口 → 未开始下游：保持灰虚线（进度只体现在连入运行节点的边上）
  if (prev.status === "in_progress") return resolve("pending", false);
  if (next.status === "in_progress") return resolve("active", !next.stalled);
  if (next.status === "awaiting_human") {
    if (prev.status === "completed") return resolve("await", false);
    return resolve("pending", false);
  }
  if (prev.status === "completed" && next.status === "completed") return resolve("done", false);
  if (
    prev.status === "completed" &&
    next.is_next &&
    (next.status === "pending" || !next.status)
  ) {
    return resolve("active", true);
  }
  return resolve("pending", false);
}

/** 图例文案（与上表一致，供工具栏展示） */
export const EDGE_LEGEND = [
  {lineStyle: "solid" as const, color: "green", label: "实线·绿 = 已完成"},
  {lineStyle: "solid" as const, color: "blue", label: "实线·蓝 + 光点 = 连入进行中节点"},
  {lineStyle: "solid" as const, color: "amber", label: "实线·琥珀 = 待审批"},
  {lineStyle: "dashed" as const, color: "gray", label: "虚线·灰 = 未接通"},
  {lineStyle: "dashed" as const, color: "red", label: "虚线·红 = 失败"},
];
