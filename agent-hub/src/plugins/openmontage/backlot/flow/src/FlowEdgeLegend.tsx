import {EDGE_LEGEND} from "./edgeStyle";

/** 工具栏连线图例 — 与 EDGE_VISUAL_SPEC.md / edgeStyle.ts 一致 */
export function FlowEdgeLegend() {
  return (
    <div className="fs-edge-legend" aria-label="连线图例">
      {EDGE_LEGEND.map((item) => (
        <span key={item.label} className="fs-edge-legend-item" title={item.label}>
          <svg className="fs-edge-legend-swatch" viewBox="0 0 40 8" aria-hidden>
            <line
              x1="2"
              y1="4"
              x2="38"
              y2="4"
              className={`fs-edge-legend-line fs-edge-legend-line--${item.color} fs-edge-legend-line--${item.lineStyle}`}
            />
            {item.lineStyle === "solid" && item.color === "blue" && (
              <circle cx="28" cy="4" r="2" className="fs-edge-legend-dot" />
            )}
          </svg>
          <span className="fs-edge-legend-text">{item.label}</span>
        </span>
      ))}
    </div>
  );
}
