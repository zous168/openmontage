// state → {nodes, edges} 推导 + 手工横向布局 + 回退自环边检测
import type {Node, Edge, XYPosition} from "@xyflow/react";
import type {BoardState, StageState, StageStatus} from "./types";
import {stageLabel, STRINGS} from "./labels";

export const NODE_W = 260;
const GAP_X = 96;

// 照 board.js renderRail 的类名映射
export function stageClass(st: StageState): string {
  if (st.status === "completed") return "done";
  if (st.status === "in_progress") return st.stalled ? "active stalled" : "active";
  if (st.status === "awaiting_human") return "await";
  if (st.status === "failed") return "failed";
  return st.is_next ? "next" : "pending";
}

export function statusCls(st: StageState): string {
  if (st.stalled) return "stalled";
  if (st.status === "completed") return "done";
  if (st.status === "in_progress") return "active";
  if (st.status === "awaiting_human") return "await";
  if (st.status === "failed") return "failed";
  return st.is_next ? "next" : "pending";
}

export interface StageNodeData {
  [key: string]: unknown;
  stage: StageState;
  selected: boolean;
  onOpen: (name: string) => void;
}

export interface InputNodeData {
  [key: string]: unknown;
  kind: "input";
  title: string;
  projectId: string;
  sourceMedia?: unknown;
  productionInputs?: Record<string, unknown>;
  selected: boolean;
  onOpen: (name: string) => void;
}

export const INPUT_NODE_ID = "input";

export type FlowNode = Node;
export type FlowEdge = Edge;

// 排名:声明序(manifest),undeclared 阶段排尾部
function rankOrder(state: BoardState): StageState[] {
  const declared = (state.pipeline?.stages ?? []).map((m) => m.name);
  const declaredSet = new Set(declared);
  const ordered: StageState[] = [];
  for (const name of declared) {
    const st = state.stages?.find((s) => s.name === name);
    if (st) ordered.push(st);
  }
  for (const st of state.stages ?? []) {
    if (st.undeclared || !declaredSet.has(st.name)) ordered.push(st);
  }
  return ordered;
}

export function buildGraph(
  state: BoardState,
  layoutRef: React.MutableRefObject<Map<string, XYPosition>>,
  selected: string | null,
  onOpen: (name: string) => void,
  projectSettings?: unknown,
): {nodes: FlowNode[]; edges: FlowEdge[]} {
  const ordered = rankOrder(state);

  // prune 陈旧位置缓存(保留 input 节点)
  const current = new Set([INPUT_NODE_ID, ...ordered.map((s) => s.name)]);
  for (const key of layoutRef.current.keys()) {
    if (!current.has(key)) layoutRef.current.delete(key);
  }

  // 输入节点(流程起点,位于最左侧)
  // 概念:输入节点 = 项目的输入(参考素材 + 需求参数)。
  // projectSettings 是项目全局配置,输入节点只消费其中的输入相关子集,
  // 全局部分(风格画册/交付规格等)不属于任何节点。
  if (!layoutRef.current.has(INPUT_NODE_ID)) {
    layoutRef.current.set(INPUT_NODE_ID, {x: -(NODE_W + GAP_X), y: 0});
  }
  const settings = (projectSettings ?? {}) as {
    source_media?: unknown;
    production_inputs?: Record<string, unknown>;
  };
  const inputNode: FlowNode = {
    id: INPUT_NODE_ID,
    type: "projectInput",
    position: layoutRef.current.get(INPUT_NODE_ID)!,
    draggable: true,
    data: {
      kind: "input",
      title: state.title ?? state.project_id,
      projectId: state.project_id,
      sourceMedia: settings.source_media ?? state.source_media,
      productionInputs: settings.production_inputs,
      selected: selected === INPUT_NODE_ID,
      onOpen,
    } as InputNodeData,
    selected: selected === INPUT_NODE_ID,
  };

  const nodes: FlowNode[] = [inputNode, ...ordered.map((st, i) => {
    if (!layoutRef.current.has(st.name)) {
      layoutRef.current.set(st.name, {x: i * (NODE_W + GAP_X), y: 0});
    }
    return {
      id: `n_${st.name}`,
      type: "stage",
      position: layoutRef.current.get(st.name)!,
      draggable: true,
      data: {
        stage: st,
        selected: selected === st.name,
        onOpen,
      },
      selected: selected === st.name,
    };
  })];

  const edges: FlowEdge[] = [];

  // 输入节点 → 首个阶段
  if (ordered.length > 0) {
    const first = ordered[0];
    edges.push({
      id: `seq:${INPUT_NODE_ID}->${first.name}`,
      source: INPUT_NODE_ID,
      target: `n_${first.name}`,
      type: "flow",
      className: first.status === "completed" ? "edge-done" : "edge-pending",
      data: {variant: (first.status === "completed" ? "done" : "pending") as "done" | "pending", flowing: false},
    });
  }

  // 顺序边
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1];
    const next = ordered[i];
    let cls: string;
    let flowing = false;
    if (prev.status === "failed") {
      // 失败节点下游：中性灰色虚线
      cls = "edge-pending";
    } else if (next.status === "failed") {
      // 连入失败节点：红色虚线
      cls = "edge-failed";
    } else if (prev.status === "awaiting_human") {
      // 上游待审批：下游不得显示为活跃/流动
      cls = "edge-pending";
    } else if (next.blocked_by_upstream) {
      cls = "edge-pending";
    } else if (next.status === "in_progress" || next.status === "awaiting_human") {
      cls = "edge-active";
      flowing = next.status === "in_progress";
    } else if (
      prev.status === "completed" &&
      next.is_next &&
      (next.status === "pending" || !next.status)
    ) {
      // 已完成 → 待运行的下一阶段：能量流向即将启动的节点
      cls = "edge-active";
      flowing = true;
    } else if (prev.status === "completed" && next.status === "completed") {
      cls = "edge-done";
    } else {
      cls = "edge-pending";
    }
    edges.push({
      id: `seq:${prev.name}->${next.name}`,
      source: `n_${prev.name}`,
      target: `n_${next.name}`,
      type: "flow",
      className: cls,
      data: {
        variant: cls.replace(/^edge-/, "") as "done" | "active" | "await" | "failed" | "pending",
        flowing,
      },
    });
  }

  return {nodes, edges};
}

export function edgeStatusLabel(st: StageState): string {
  return stageLabel(st.name);
}

// 用于 StageNode 的辅助:rail 状态文案
export function statusText(st: StageState): {text: string; cls: string} {
  if (st.status === "in_progress") {
    if (st.active_run_id) return {text: "运行中", cls: "txt-running"};
    if (st.stalled) return {text: `⚠ 可能卡住 ${st.stalled_minutes ?? "?"} 分钟`, cls: "txt-stalled"};
    if (st.partial_progress?.completed_scene_ids?.length)
      return {text: `${st.partial_progress.completed_scene_ids.length} 个场景完成`, cls: "txt-active"};
    return {text: "进行中", cls: "txt-active"};
  }
  if (st.status === "awaiting_human") return {text: STRINGS.awaitingApprovalHint, cls: "txt-await"};
  if (st.status === "failed") return {text: "失败", cls: "txt-failed"};
  if (st.status === "completed") {
    if (st.human_approved) return {text: "✓ 已批准", cls: "txt-done"};
    if (st.gate_skipped) return {text: "跳过门", cls: "txt-skip"};
    return {text: "已完成", cls: "txt-done"};
  }
  if (st.blocked_by_upstream) return {text: "等待上游", cls: "txt-blocked"};
  if (st.is_next) return {text: "下一阶段", cls: "txt-next"};
  return {text: "待开始", cls: "txt-pending"};
}

export function stageOutputs(st: StageState): string[] {
  if (st.outputs && st.outputs.length > 0) return st.outputs;
  if (st.produces && st.produces.length > 0) return st.produces;
  return [];
}

// 输入端口 = 排名靠前的已 completed 阶段 outputs(上游产物名,去 decision_log)
export function stageInputs(state: BoardState, st: StageState): string[] {
  const ordered = rankOrder(state);
  const idx = ordered.findIndex((s) => s.name === st.name);
  if (idx <= 0) return [];
  const upstream: string[] = [];
  for (let i = 0; i < idx; i++) {
    const prev = ordered[i];
    if (prev.status !== "completed") continue;
    for (const o of stageOutputs(prev)) {
      if (o !== "decision_log" && !upstream.includes(o)) upstream.push(o);
    }
  }
  return upstream;
}

// 上游产物对应的 artifact 值(供参考槽展示)
export function upstreamArtifacts(
  state: BoardState,
  st: StageState,
): {name: string; value: unknown}[] {
  const names = stageInputs(state, st);
  const arts = state.artifacts ?? {};
  return names
    .filter((n) => arts[n] !== undefined)
    .map((n) => ({name: n, value: arts[n]}));
}
