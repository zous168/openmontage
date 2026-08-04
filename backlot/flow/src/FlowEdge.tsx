import {BaseEdge, getBezierPath, type EdgeProps} from "@xyflow/react";

export interface FlowEdgeData {
  variant?: "done" | "active" | "await" | "failed" | "pending";
  flowing?: boolean;
  [key: string]: unknown;
}

const STROKE: Record<string, string> = {
  done: "var(--green, #3ddc84)",
  active: "var(--accent, #4da3ff)",
  await: "var(--amber, #f0b429)",
  failed: "var(--red, #ff5c5c)",
  pending: "var(--border, #2a3040)",
};

const DASH = "7 9";

/** 流水线边：流动态为虚线沿路径滑向目标节点 */
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
  const flowing = edgeData.flowing === true;
  const stroke = STROKE[variant] ?? STROKE.pending;

  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  if (flowing) {
    return (
      <>
        {/* 虚线底轨 */}
        <BaseEdge
          id={id}
          path={edgePath}
          markerEnd={markerEnd}
          style={{
            ...style,
            stroke,
            strokeWidth: 2,
            strokeDasharray: DASH,
            opacity: 0.28,
          }}
        />
        {/* 虚线流动层 */}
        <path
          className="fs-edge-flow-dash"
          d={edgePath}
          fill="none"
          stroke={stroke}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeDasharray={DASH}
        />
      </>
    );
  }

  const dashed = variant === "pending" || variant === "failed";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke,
          strokeWidth: 2,
          strokeDasharray: dashed ? DASH : undefined,
          opacity: dashed ? 0.85 : 1,
        }}
      />
      {variant === "await" && (
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
