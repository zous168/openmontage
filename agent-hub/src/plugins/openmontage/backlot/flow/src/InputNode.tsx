import {Handle, Position, type NodeProps} from "@xyflow/react";
import {memo} from "react";
import type {SourceMedia} from "./types";
import type {InputNodeData} from "./graph";
import {thumbURL} from "./media";

type InputNodeProps = NodeProps & {data: InputNodeData};

function InputNodeInner({data}: InputNodeProps) {
  const sm = data.sourceMedia as SourceMedia | undefined;
  const inputs = data.productionInputs ?? {};
  const refUrl = typeof inputs.reference_url === "string" ? inputs.reference_url : "";
  const platform = typeof inputs.target_platform === "string" ? inputs.target_platform : "";
  const duration = inputs.target_duration_seconds;

  return (
    <div className={`flow-stage flow-input${data.selected ? " selected" : ""}`} onClick={() => data.onOpen("input")}>
      {/* 输出端口(右侧,连向首个阶段) */}
      <div className="fs-ports fs-ports-out">
        <div className="fs-port">
          <span className="fs-port-label">输入产物</span>
          <Handle type="source" position={Position.Right} id="out:input" className="fs-handle" />
        </div>
      </div>

      <div className="fs-head">
        <span className="fs-badge fs-badge--input">⏵ 输入</span>
      </div>

      <div className="fs-name">
        {data.title}
        <span className="fs-name-en">INPUT</span>
      </div>

      {/* 参考素材摘要 */}
      <div className="fs-input-media">
        {sm?.poster && (
          <img
            className="fs-input-poster"
            src={thumbURL(data.projectId, String(sm.poster), 240)}
            alt=""
          />
        )}
        <div className="fs-input-media-body">
          {refUrl && (
            <div className="fs-input-url" title={refUrl}>
              {refUrl.replace(/^https?:\/\//, "").slice(0, 40)}
            </div>
          )}
          {!refUrl && sm?.path && <div className="fs-input-url">{String(sm.path).split("/").pop()}</div>}
          {!refUrl && !sm?.path && <div className="fs-input-url">（无参考素材）</div>}
          {sm?.summary && <div className="fs-input-summary">{String(sm.summary).slice(0, 80)}</div>}
        </div>
      </div>

      {/* 需求参数 chips(输入相关,来自 production_inputs) */}
      <div className="fs-input-chips">
        {platform && <span className="fs-chip-sm">{platform}</span>}
        {duration != null && <span className="fs-chip-sm">{String(duration)}s</span>}
        {typeof inputs.topic === "string" && inputs.topic && <span className="fs-chip-sm">话题</span>}
      </div>
    </div>
  );
}

export const InputNode = memo(InputNodeInner);
