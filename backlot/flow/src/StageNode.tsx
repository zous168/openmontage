import {Handle, Position, type NodeProps} from "@xyflow/react";
import type {StageState} from "./types";
import {railStatusLabel, stageLabel} from "./labels";
import {stageClass, statusCls, statusText, type StageNodeData} from "./graph";

const ICONS: Record<string, string> = {
  completed: "✓",
  in_progress: "◉",
  awaiting_human: "◈",
  failed: "✕",
};

/** 圆角矩形边框路径（viewBox 0 0 100 100），供电流光点沿边流动 */
const BORDER_PATH =
  "M 6.7 1.2 H 93.1 A 5.5 5.5 0 0 1 98.8 6.7 V 93.1 A 5.5 5.5 0 0 1 93.1 98.8 H 6.7 A 5.5 5.5 0 0 1 1.2 93.1 V 6.7 A 5.5 5.5 0 0 1 6.7 1.2 Z";

function BorderCurrent({stalled}: {stalled?: boolean}) {
  const dur = "2.2s";
  const dotCls = stalled ? " fs-border-flow-dot--stalled" : "";
  return (
    <svg className="fs-border-flow" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      <path
        className={`fs-border-flow-track${stalled ? " fs-border-flow-track--stalled" : ""}`}
        d={BORDER_PATH}
        fill="none"
        vectorEffect="non-scaling-stroke"
      />
      <circle className={`fs-border-flow-dot fs-border-flow-dot--glow${dotCls}`} r={6}>
        <animateMotion dur={dur} repeatCount="indefinite" path={BORDER_PATH} calcMode="linear" />
      </circle>
      <circle className={`fs-border-flow-dot fs-border-flow-dot--core${dotCls}`} r={3}>
        <animateMotion dur={dur} repeatCount="indefinite" path={BORDER_PATH} calcMode="linear" />
      </circle>
    </svg>
  );
}

type StageNodeProps = NodeProps & {data: StageNodeData};

export function StageNode({data}: StageNodeProps) {
  const st: StageState = data.stage;
  const cls = stageClass(st);
  const scls = statusCls(st);
  const icon = ICONS[st.status] ?? "";
  const stText = statusText(st);
  const badge = railStatusLabel(st);
  const versions = st.versions ?? 1;
  const sceneDone = st.partial_progress?.completed_scene_ids?.length ?? 0;

  return (
    <div
      className={`flow-stage ${cls}${data.selected ? " selected" : ""}${st.undeclared ? " undeclared" : ""}`}
      title={st.undeclared ? `未声明阶段: ${st.name}` : undefined}
    >
      <Handle type="target" position={Position.Left} className="fs-handle fs-handle--in" />
      <Handle type="source" position={Position.Right} className="fs-handle fs-handle--out" />

      {st.status === "in_progress" && <BorderCurrent stalled={st.stalled} />}

      <div className="fs-head">
        <span className={`fs-badge fs-badge--${scls}`}>
          {icon} {badge}
        </span>
        {st.gated && st.status !== "awaiting_human" && (
          <span className={`fs-gate${st.gate_skipped ? " fs-gate--skip" : ""}`} title={st.gate_skipped ? "已跳过审批门" : "需要审批门"}>
            ◈
          </span>
        )}
        {versions > 1 && <span className="fs-ver">v{versions}</span>}
        {st.status === "pending" && (st.versions ?? 0) > 0 && <span className="fs-reset">已重置</span>}
      </div>

      <div className="fs-name">
        {stageLabel(st.name)}
        <span className="fs-name-en">{st.name}</span>
      </div>

      {stText.text ? (
        <div className={`fs-status ${stText.cls}`}>
          {st.status === "in_progress" && <span className="fs-pulse" />}
          {stText.text}
        </div>
      ) : null}

      {sceneDone > 0 && (
        <div className="fs-scene-progress" title={`${sceneDone} 个场景已完成`}>
          <div className="fs-scene-progress-bar" style={{width: `${Math.min(100, sceneDone * 12)}%`}} />
          <span className="fs-scene-progress-label">{sceneDone} 场景</span>
        </div>
      )}
    </div>
  );
}
