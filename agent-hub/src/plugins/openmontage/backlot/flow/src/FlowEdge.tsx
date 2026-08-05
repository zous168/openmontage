import {BaseEdge, getBezierPath, type EdgeProps} from "@xyflow/react";
import type {EdgeLineStyle, EdgeVariant} from "./edgeStyle";

export interface FlowEdgeData {
  variant?: EdgeVariant;
  lineStyle?: EdgeLineStyle;
  flowing?: boolean;
  [key: string]: unknown;
}

const STROKE: Record<EdgeVariant, string> = {
  done: "var(--green, #3ddc84)",
  active: "var(--accent, #4da3ff)",
  await: "var(--amber, #f0b429)",
  failed: "var(--red, #ff5c5c)",
  pending: "var(--border, #2a3040)",
};

const DASH = "7 9";

/**
 * 流水线边渲染：
 * - 实线：done / active / await
 * - 虚线：pending / failed
 * - 进行中进度：蓝色实线 + 沿路径流动光点（不用虚线表示进行中）
 */
export function FlowEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    markerEnd,
    style,
  } = props;

  const edgeData = (data ?? {}) as FlowEdgeData;
  const variant = edgeData.variant ?? "pending";
  const lineStyle: EdgeLineStyle =
    edgeData.lineStyle ?? (variant === "pending" || variant === "failed" ? "dashed" : "solid");
  const flowing = edgeData.flowing === true && lineStyle === "solid" && variant === "active";
  const stroke = STROKE[variant] ?? STROKE.pending;
  const dashed = lineStyle === "dashed";

  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      {flowing && (
        <BaseEdge
          id={`${id}-track`}
          path={edgePath}
          style={{
            ...style,
            stroke,
            strokeWidth: 2,
            opacity: 0.22,
          }}
        />
      )}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke,
          strokeWidth: flowing ? 2.5 : 2,
          strokeDasharray: dashed ? DASH : undefined,
          opacity: dashed ? 0.85 : 1,
        }}
      />
      {flowing && (
        <>
          <circle className="fs-edge-flow-dot fs-edge-flow-dot--glow" r={5} fill={stroke}>
            <animateMotion dur="1.35s" repeatCount="indefinite" path={edgePath} calcMode="linear" />
          </circle>
          <circle className="fs-edge-flow-dot fs-edge-flow-dot--core" r={2.5} fill="#fff">
            <animateMotion dur="1.35s" repeatCount="indefinite" path={edgePath} calcMode="linear" />
          </circle>
        </>
      )}
      {variant === "await" && !flowing && (
        <path
          d={edgePath}
          fill="none"
          stroke="rgba(240, 180, 41, 0.35)"
          strokeWidth={5}
          strokeLinecap="round"
        />
      )}
    </>
  );
}
