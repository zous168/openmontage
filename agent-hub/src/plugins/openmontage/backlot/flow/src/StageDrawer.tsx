// 底部操作框(RunHub 式):选中节点 → 画布底部浮出。
// 看:本节点内容预览 + 参考槽 | 改:核心信息表单
// 批准/运行/日志等操作在标题栏右侧(无「做」Tab)
import {useEffect, useMemo, useState} from "react";
import type {BoardState, ProjectSettings, RunState, StageOutputItem, StageState} from "./types";
import {artifactLabel, railStatusLabel, stageLabel, STRINGS} from "./labels";
import {stageOutputs, statusCls, upstreamOutputDecl} from "./graph";
import {kindOfPath, mediaURL as buildMediaURL, thumbURL} from "./media";
import {getJSON, patchJSON, postJSON} from "./api";
import {getCoreFields, type CoreField} from "./coreFields";
import {optionLabel} from "./fieldLabels";
import {fetchVideoProviderOptions, providerOptionsForDecision, type VideoProviderOption} from "./videoProviders";
import {
  ProviderToolbar,
  providerBarFromInputs,
  providerBarPatch,
  type ProviderBarValues,
} from "./ProviderToolbar";
import {
  failureMessage,
  filterRunLogLines,
  latestRunForStage,
  failedRunForStage,
  runLogPreview,
} from "./stageFailure";

interface Props {
  state: BoardState;
  stage: StageState | null;
  isInput?: boolean;
  projectSettings?: ProjectSettings | null;
  settings: Record<string, unknown>;
  onSettingsChange: (settings: Record<string, unknown>) => void;
  onClose: () => void;
  onChanged: () => void;
}

// 从 state.artifacts 按路径取值(预填表单)
function pickArtifact(artifacts: Record<string, unknown> | undefined, path: string[]): unknown {
  if (!artifacts) return undefined;
  let cur: unknown = artifacts;
  for (const seg of path) {
    if (cur && typeof cur === "object" && seg in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return cur;
}

function fieldValue(
  field: CoreField,
  settings: Record<string, unknown>,
  artifacts: Record<string, unknown> | undefined,
  productionInputs?: Record<string, unknown>,
): string {
  const set = settings[field.key];
  if (set !== undefined && set !== null && set !== "") return String(set);
  if (field.productionInputKey && productionInputs?.[field.productionInputKey] != null) {
    return String(productionInputs[field.productionInputKey]);
  }
  const art = pickArtifact(artifacts, field.artifactPath);
  if (art !== undefined && art !== null) {
    if (Array.isArray(art)) return String(art.length);
    return String(art);
  }
  return "";
}

function stageRunParameters(settings: Record<string, unknown>): Record<string, unknown> {
  const params = {...settings};
  const pref = settings.preferred_video_provider ?? settings.preferred_provider;
  if (pref != null && String(pref).trim() !== "") {
    params.preferred_provider = pref;
  }
  return params;
}

function selectOptionsForField(
  field: CoreField,
  videoProviders: VideoProviderOption[],
  playbookLabels: Record<string, string>,
): {value: string; label: string; disabled?: boolean}[] {
  if (field.dynamicOptions === "video_providers" && videoProviders.length > 0) {
    return videoProviders.map((o) => ({
      value: o.value,
      label: o.label,
      disabled: !o.available && o.value !== "auto",
    }));
  }
  return (field.options ?? []).map((o) => ({
    value: o,
    label: optionLabel(field.key, o, playbookLabels),
  }));
}

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", {hour12: false});
}

/** 与 board.js nextRunStage 对齐：第一个未完成阶段（含 failed 重跑） */
function nextRunTarget(state: BoardState): {name: string; label: string} | null {
  const liveRun = state.runs?.find((r) => r.status === "queued" || r.status === "running");
  if (liveRun) return null;
  if (state.stages?.some((s) => s.status === "awaiting_human")) return null;

  const nextName = state.next_stage;
  const next = nextName ? state.stages?.find((s) => s.name === nextName) : null;
  if (next && next.status === "pending") {
    const idx = state.stages!.findIndex((s) => s.name === nextName);
    const prev = idx > 0 ? state.stages![idx - 1] : null;
    if (prev?.status === "completed") return null;
  }

  const target = state.stages?.find((s) => !s.undeclared && s.status !== "completed");
  if (!target) return null;
  return {name: target.name, label: stageLabel(target.name)};
}

/** 当前选中节点是否可手动运行/重试 */
function runTargetForStage(
  state: BoardState,
  stage: StageState,
): {name: string; label: string; retry: boolean} | null {
  const liveRun = state.runs?.find((r) => r.status === "queued" || r.status === "running");
  if (liveRun) return null;
  if (state.stages?.some((s) => s.status === "awaiting_human")) return null;

  // failed 且为 get_next_stage 指向的阶段 → 始终显示重试（不依赖 nextRunTarget 启发式）
  if (stage.status === "failed" && stage.name === state.next_stage) {
    return {name: stage.name, label: stageLabel(stage.name), retry: true};
  }

  const target = nextRunTarget(state);
  if (!target || target.name !== stage.name) return null;
  return {...target, retry: stage.status === "failed"};
}

// ---- 看区:内容预览(按阶段类型) ----
function PreviewPane({
  state,
  stage,
  playbookLabels,
}: {
  state: BoardState;
  stage: StageState;
  playbookLabels: Record<string, string>;
}) {
  const arts = state.artifacts ?? {};
  const outputs = stageOutputs(stage);
  const art = outputs.length > 0 ? arts[outputs[0]] : undefined;
  const stName = stage.name;

  if (stName === "script" && art && typeof art === "object" && "sections" in art) {
    const sections = (art as {sections?: {label?: string; text?: string}[]}).sections ?? [];
    return (
      <div className="fs-preview">
        {sections.slice(0, 8).map((s, i) => (
          <div key={i} className="fs-preview-block">
            <div className="fs-preview-label">{s.label ?? `段落 ${i + 1}`}</div>
            <div className="fs-preview-text">{String(s.text ?? "").slice(0, 180)}</div>
          </div>
        ))}
      </div>
    );
  }
  if (stName === "proposal" && art && typeof art === "object") {
    const a = art as {selected_concept?: unknown; production_plan?: Record<string, unknown>; cost_estimate?: Record<string, unknown>};
    const plan = a.production_plan ?? {};
    const cost = a.cost_estimate ?? {};
    return (
      <div className="fs-preview">
        <div className="fs-preview-row"><b>渲染引擎</b> {optionLabel("render_runtime", String(plan.render_runtime ?? ""))}</div>
        <div className="fs-preview-row"><b>渲染族</b> {optionLabel("renderer_family", String(plan.renderer_family ?? ""))}</div>
        <div className="fs-preview-row"><b>风格画册</b> {optionLabel("playbook", String(plan.playbook ?? ""), playbookLabels)}</div>
        <div className="fs-preview-row"><b>预算上限</b> ${String(cost.budget_cap_usd ?? "—")}</div>
        <div className="fs-preview-row"><b>总估算</b> ${String(cost.total_estimated_usd ?? "—")}</div>
      </div>
    );
  }
  if (stName === "scene_plan" && art && typeof art === "object" && "scenes" in art) {
    const scenes = (art as {scenes?: {type?: string; description?: string}[]}).scenes ?? [];
    return (
      <div className="fs-preview">
        {scenes.slice(0, 10).map((s, i) => (
          <div key={i} className="fs-preview-row">
            <b>#{i + 1}</b> {String(s.type ?? "")} — {String(s.description ?? "").slice(0, 80)}
          </div>
        ))}
      </div>
    );
  }
  if (stName === "compose" && art && typeof art === "object" && "outputs" in art) {
    const outs = (art as {outputs?: {path?: string; format?: string; resolution?: string; duration_seconds?: number}[]}).outputs ?? [];
    if (outs.length === 0) return null;
    return (
      <div className="fs-preview">
        {outs.map((o, i) => (
          <div key={i} className="fs-preview-row">
            <b>输出 {i + 1}</b> {String(o.format ?? "")} · {String(o.resolution ?? "")}
            {o.duration_seconds != null ? ` · ${o.duration_seconds.toFixed(1)}s` : ""}
            {o.path ? ` · ${String(o.path).split("/").pop()}` : null}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="fs-preview">
      <div className="fs-muted">本阶段暂无结构化预览{outputs.length > 0 ? `(产物: ${outputs.map(artifactLabel).join(" / ")})` : ""}</div>
    </div>
  );
}

// ---- 按 manifest outputs 声明(source 表达式)从产物提取输出卡 ----
// 语法:点路径 + [] 展开数组,如 "assets[].path" / "render_report.outputs[].path"。
// 根默认是 artifacts 顶层;第一段不在顶层且唯一产物含该键时剥壳。

function extractSource(source: string, artifacts: Record<string, unknown>): unknown[] {
  const segs = source.split(".").map((p) =>
    p.endsWith("[]")
      ? {kind: "list" as const, key: p.slice(0, -2)}
      : {kind: "key" as const, key: p},
  );
  if (segs.some((s) => !s.key)) return [];
  let root: unknown = artifacts;
  const first = segs[0].key;
  if (typeof root === "object" && root !== null && !(first in (root as Record<string, unknown>))) {
    const cands = Object.values(root as Record<string, unknown>).filter(
      (v) => typeof v === "object" && v !== null && first in (v as Record<string, unknown>),
    );
    if (cands.length === 1) root = cands[0];
  }
  const results: unknown[] = [];
  const walk = (obj: unknown, idx: number, depth: number) => {
    if (idx >= segs.length) { results.push(obj); return; }
    if (depth > 8 || results.length >= 12) return;
    const {kind, key} = segs[idx];
    if (kind === "list") {
      const items = typeof obj === "object" && obj !== null ? (obj as Record<string, unknown>)[key] : undefined;
      if (Array.isArray(items)) for (const it of items) walk(it, idx + 1, depth + 1);
    } else if (typeof obj === "object" && obj !== null && key in (obj as Record<string, unknown>)) {
      walk((obj as Record<string, unknown>)[key], idx + 1, depth + 1);
    }
  };
  walk(root, 0, 0);
  return results;
}

type ManifestIODecl = {kind: string; label: string; source?: string | null};

function declaredFromManifest(
  decl: ManifestIODecl[],
  arts: Record<string, unknown>,
): StageOutputItem[] {
  const cards: StageOutputItem[] = [];
  const seen = new Set<string>();
  for (const d of decl) {
    if (d.kind === "data") {
      const v = arts[d.label];
      if (v != null) cards.push({kind: "data", label: d.label, data: v as Record<string, unknown>});
      continue;
    }
    // text 无 source：整份产物 JSON（label = artifact 名）
    if (d.kind === "text" && !d.source) {
      const v = arts[d.label];
      if (v != null && typeof v === "object") {
        cards.push({
          kind: "data",
          label: artifactLabel(d.label),
          data: v as Record<string, unknown>,
        });
      }
      continue;
    }
    if (!d.source) continue;
    for (const val of extractSource(d.source, arts)) {
      if (cards.length >= 12) break;
      if (d.kind === "text") {
        let text: string;
        if (typeof val === "string") text = val;
        else if (val != null && typeof val === "object") text = JSON.stringify(val);
        else if (val != null) text = String(val);
        else text = "";
        if (text.trim() && !seen.has(text)) {
          seen.add(text);
          cards.push({kind: "text", label: d.label, text: text.trim()});
        }
      } else if (typeof val === "string") {
        const k = kindOfPath(val);
        if (k !== "text" && !seen.has(val)) {
          seen.add(val);
          cards.push({kind: k, label: d.label, path: val});
        }
      }
    }
  }
  return cards;
}

// 按 stage 的 outputs 声明推导输出卡
function declaredOutputs(state: BoardState, stage: StageState): StageOutputItem[] {
  const decl = state.pipeline?.stages?.find((s) => s.name === stage.name)?.outputs ?? [];
  return declaredFromManifest(decl, state.artifacts ?? {});
}

// 输入 = 上游 stage 的 outputs 声明
function declaredInputs(state: BoardState, stage: StageState): StageOutputItem[] {
  return declaredFromManifest(upstreamOutputDecl(state, stage), state.artifacts ?? {});
}

// 声明缺失时的兜底:产物原样 JSON(媒体嵌在树里)
function fallbackViews(state: BoardState, stage: StageState): {label: string; value: unknown}[] {
  const arts = state.artifacts ?? {};
  return stageOutputs(stage)
    .filter((n) => arts[n] != null)
    .map((n) => ({label: artifactLabel(n), value: arts[n]}));
}

// ---- 输入区:上游 stage outputs(上游输出 = 下游输入) ----
function InputSlot({state, stage}: {state: BoardState; stage: StageState}) {
  const cards = useMemo(() => declaredInputs(state, stage), [state, stage]);
  const media = cards.filter((c) => c.kind !== "data" && c.kind !== "text");
  const textItems = cards
    .filter((c) => c.kind === "data")
    .map((o, i) => ({id: `in-${o.label}-${i}`, label: o.label, artifact: o.data}));
  return (
    <div className="fs-refs">
      <div className="fs-refs-label">输入 · 上游产物</div>
      {cards.length > 0 ? (
        <ArtifactStrip
          projectId={state.project_id}
          mediaItems={media}
          textItems={textItems}
        />
      ) : (
        <div className="fs-muted">暂无输入 · 等待上游完成</div>
      )}
    </div>
  );
}

// 参考区:参考素材(项目的参考视频/图/URL)+ 可追加的产物(辅助参考,非必需)
function ReferenceSlot({
  state, extraRefs, onAddRef, onRemoveRef,
}: {
  state: BoardState;
  extraRefs: string[];
  onAddRef: (name: string) => void;
  onRemoveRef: (name: string) => void;
}) {
  const arts = state.artifacts ?? {};
  const [picking, setPicking] = useState(false);
  const available = Object.keys(arts).filter(
    (n) => !extraRefs.includes(n) && n !== "decision_log",
  );
  // 项目参考素材(source_media:参考视频/图/URL)
  const sourceRefs = useMemo(() => {
    const sm = state.source_media;
    const out: StageOutputItem[] = [];
    if (sm?.path) {
      out.push({
        kind: sm.playable ? "video" : "image",
        label: "参考素材",
        path: sm.path,
      });
    }
    if (sm?.poster) {
      out.push({kind: "image", label: "参考帧", path: sm.poster});
    }
    return out;
  }, [state.source_media]);

  return (
    <div className="fs-refs">
      <div className="fs-refs-label">参考素材(辅助)</div>
      <ArtifactStrip
        projectId={state.project_id}
        mediaItems={sourceRefs}
        textItems={extraRefs.map((n) => ({
          id: n,
          label: artifactLabel(n),
          artifact: arts[n],
          removable: true,
        }))}
        onRemoveText={onRemoveRef}
      />
      {sourceRefs.length === 0 && extraRefs.length === 0 && (
        <div className="fs-muted">暂无参考素材(可追加产物)</div>
      )}
      <div className="fs-refs-add">
        <button className="fs-btn" onClick={() => setPicking(!picking)}>＋ 追加参考</button>
        {picking && available.length > 0 && (
          <select
            className="fs-refs-select"
            value=""
            onChange={(e) => {
              if (e.target.value) onAddRef(e.target.value);
              setPicking(false);
            }}
          >
            <option value="">选择产物…</option>
            {available.map((n) => (
              <option key={n} value={n}>{artifactLabel(n)} ({n})</option>
            ))}
          </select>
        )}
        {picking && available.length === 0 && <span className="fs-muted">没有可追加的产物</span>}
      </div>
    </div>
  );
}

// compose / publish:成片优先内嵌播放器,避免只看见 JSON 卡
function OutputHeroVideos({
  projectId,
  videos,
}: {
  projectId: string;
  videos: StageOutputItem[];
}) {
  if (videos.length === 0) return null;
  return (
    <div className="fs-output-hero">
      {videos.map((o, i) => {
        const url = o.path ? buildMediaURL(projectId, o.path) : null;
        if (!url || o.kind !== "video") return null;
        return (
          <div key={`hero-${o.path ?? i}`} className="fs-output-hero-item">
            <div className="fs-output-hero-label">{o.label}</div>
            <video className="fs-preview-video" src={url} controls preload="metadata" />
          </div>
        );
      })}
    </div>
  );
}

// 本节点输出 = 按 manifest outputs 声明推导:媒体文件(资产/渲染视频)平铺 + 产物 JSON
function OutputGrid({state, stage}: {state: BoardState; stage: StageState}) {
  const cards = declaredOutputs(state, stage);
  const fallback = cards.length === 0 ? fallbackViews(state, stage) : [];
  if (cards.length === 0 && fallback.length === 0) return null;

  const media = cards.filter((c) => c.kind !== "data" && c.kind !== "text");
  const videos = media.filter((c) => c.kind === "video");
  const showHero = (stage.name === "compose" || stage.name === "publish") && videos.length > 0;
  const textItems = [
    ...cards
      .filter((c) => c.kind === "data")
      .map((o, i) => ({id: `data-${o.label}-${i}`, label: o.label, artifact: o.data})),
    ...cards
      .filter((c) => c.kind === "text")
      .map((o, i) => ({id: `text-${o.label}-${i}`, label: o.label, artifact: o.text ?? ""})),
    ...fallback.map(({label, value}) => ({id: `fb-${label}`, label, artifact: value})),
  ];

  return (
    <>
      {showHero && <OutputHeroVideos projectId={state.project_id} videos={videos} />}
      <ArtifactStrip
        projectId={state.project_id}
        mediaItems={media}
        textItems={textItems}
      />
    </>
  );
}

function artifactFieldCount(artifact: unknown): number {
  if (artifact && typeof artifact === "object" && !Array.isArray(artifact)) {
    return Object.keys(artifact as Record<string, unknown>).length;
  }
  if (Array.isArray(artifact)) return artifact.length;
  return 0;
}

function artifactToJson(artifact: unknown): string {
  if (typeof artifact === "string") return artifact;
  try {
    return JSON.stringify(artifact ?? null, null, 2);
  } catch {
    return String(artifact ?? "");
  }
}

// JSON 产物模态框
function ArtifactModal({
  label,
  artifact,
  onClose,
}: {
  label: string;
  artifact: unknown;
  onClose: () => void;
}) {
  const json = useMemo(() => artifactToJson(artifact), [artifact]);
  const fieldCount = useMemo(() => artifactFieldCount(artifact), [artifact]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fs-modal" onClick={onClose}>
      <div className="fs-modal-body fs-modal-body--json" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="fs-modal-close" onClick={onClose} aria-label="关闭">✕</button>
        <div className="fs-modal-title">
          {label}
          {fieldCount > 0 ? ` · ${fieldCount} 字段` : ""}
        </div>
        <pre className="fs-modal-json">{json}</pre>
      </div>
    </div>
  );
}

// 产物条:图2式 — 图片缩略卡 + 文本卡,同一行,点击模态框查看
function MediaTile({
  output,
  projectId,
  onOpen,
}: {
  output: StageOutputItem;
  projectId: string;
  onOpen: () => void;
}) {
  const url = output.path ? buildMediaURL(projectId, output.path) : null;

  if (output.kind === "audio" && url) {
    return (
      <div className="fs-artifact-tile fs-artifact-tile--audio" title={output.label}>
        <span className="fs-artifact-tile-kind">音频</span>
        <span className="fs-artifact-tile-label">{output.label}</span>
        <audio className="fs-artifact-tile-audio" src={url} controls preload="none" />
      </div>
    );
  }

  if (!url) return null;

  return (
    <button
      type="button"
      className="fs-artifact-tile fs-artifact-tile--media"
      onClick={onOpen}
      title={`查看 ${output.label}`}
    >
      <img
        className="fs-artifact-tile-thumb"
        src={thumbURL(projectId, output.path!, 240)}
        alt={output.label}
        loading="lazy"
      />
      <span className="fs-artifact-tile-label">
        {output.kind === "video" ? "▶ " : ""}
        {output.label}
      </span>
    </button>
  );
}

function ArtifactStrip({
  projectId,
  textItems = [],
  mediaItems = [],
  onRemoveText,
}: {
  projectId: string;
  textItems?: {id: string; label: string; artifact: unknown; removable?: boolean}[];
  mediaItems?: StageOutputItem[];
  onRemoveText?: (id: string) => void;
}) {
  const [openTextId, setOpenTextId] = useState<string | null>(null);
  const [openMedia, setOpenMedia] = useState<StageOutputItem | null>(null);
  const openText = textItems.find((it) => it.id === openTextId) ?? null;

  if (!textItems.length && !mediaItems.length) return null;

  return (
    <>
      <div className="fs-artifact-strip">
        {mediaItems.map((o, i) => (
          <MediaTile
            key={`m-${o.path ?? o.label}-${i}`}
            output={o}
            projectId={projectId}
            onOpen={() => setOpenMedia(o)}
          />
        ))}
        {textItems.map((it) => (
          <div key={it.id} className="fs-artifact-tile-wrap">
            <button
              type="button"
              className="fs-artifact-tile fs-artifact-tile--text"
              onClick={() => setOpenTextId(it.id)}
              title={`查看 ${it.label}`}
            >
              <span className="fs-artifact-tile-kind">文本</span>
              <span className="fs-artifact-tile-label">{it.label}</span>
            </button>
            {it.removable && onRemoveText && (
              <button
                type="button"
                className="fs-artifact-tile-x"
                onClick={() => onRemoveText(it.id)}
                title="移除参考"
                aria-label="移除参考"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>
      {openText && (
        <ArtifactModal
          label={openText.label}
          artifact={openText.artifact}
          onClose={() => setOpenTextId(null)}
        />
      )}
      {openMedia && (
        <MediaModal output={openMedia} projectId={projectId} onClose={() => setOpenMedia(null)} />
      )}
    </>
  );
}

// 媒体弹框:全屏模态显示视频/图片(点击遮罩或 Esc 关闭)
function MediaModal({output, projectId, onClose}: {output: StageOutputItem; projectId: string; onClose: () => void}) {
  const url = output.path ? buildMediaURL(projectId, output.path) : null;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!url) return null;
  return (
    <div className="fs-modal" onClick={onClose}>
      <div className="fs-modal-body" onClick={(e) => e.stopPropagation()}>
        <button className="fs-modal-close" onClick={onClose} aria-label="关闭">✕</button>
        <div className="fs-modal-title">{output.label}</div>
        {output.kind === "video" ? (
          <video className="fs-modal-media" src={url} controls autoPlay />
        ) : (
          <img className="fs-modal-media" src={url} alt={output.label} />
        )}
      </div>
    </div>
  );
}

// ---- 主组件:底部操作框 ----
export function StageDrawer({state, stage, isInput, projectSettings, settings, onSettingsChange, onClose, onChanged}: Props) {
  // 输入节点:看(参考素材/参数)+ 改(production_inputs → PATCH /settings)
  if (isInput) {
    return <InputOps state={state} projectSettings={projectSettings ?? null} onClose={onClose} onChanged={onChanged} />;
  }
  const [tab, setTab] = useState<"see" | "edit">("see");
  const [feedback, setFeedback] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [logText, setLogText] = useState<string | null>(null);
  const [runDetailsOpen, setRunDetailsOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [extraRefs, setExtraRefs] = useState<string[]>([]);
  const [playbookLabels, setPlaybookLabels] = useState<Record<string, string>>({});
  const [videoProviders, setVideoProviders] = useState<VideoProviderOption[]>([]);
  const [providerBar, setProviderBar] = useState<ProviderBarValues>({
    preferred_video_provider: "",
    quality_tier: "",
    aspect_ratio: "",
    video_gen_clip_duration_seconds: "",
  });

  useEffect(() => {
    getJSON("/api/style-playbooks")
      .then((opts: {value?: string; label_zh?: string}[]) => {
        const map: Record<string, string> = {};
        for (const o of opts ?? []) {
          if (o.value) map[o.value] = o.label_zh || o.value;
        }
        setPlaybookLabels(map);
      })
      .catch(() => {});
    fetchVideoProviderOptions().then(setVideoProviders).catch(() => {});
  }, []);

  const productionInputs = projectSettings?.production_inputs ?? {};
  const st = stage!;
  const artifacts = state.artifacts ?? {};
  const activeRun =
    state.runs?.find((r) => r.task_id === st.active_run_id)
    ?? state.runs?.find(
      (r) => r.stage === st.name && (r.status === "queued" || r.status === "running"),
    );
  const failedRun = failedRunForStage(state, st.name);
  const logRun = latestRunForStage(state, st.name) ?? failedRun;
  const failureMsg = failureMessage(st, state);
  const runLogHint = runLogPreview(logRun);
  const scls = statusCls(st);
  const coreFields = getCoreFields(st.name).filter((f) => f.key !== "preferred_video_provider");
  const hasProviderBar = getCoreFields(st.name).some((f) => f.key === "preferred_video_provider");
  const runTarget = runTargetForStage(state, st);

  useEffect(() => {
    setProviderBar(providerBarFromInputs(productionInputs, projectSettings?.deliverable ?? state.deliverable));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st.name, projectSettings?.project_id]);

  useEffect(() => {
    const init: Record<string, string> = {};
    for (const f of coreFields) init[f.key] = fieldValue(f, settings, artifacts, productionInputs);
    setDraft(init);
    setFeedback("");
    setRejecting(false);
    setErr(null);
    setLogText(null);
    setRunDetailsOpen(false);
    setTab("see");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st.name, st.status]);

  const saveCore = async () => {
    setBusy(true);
    setErr(null);
    try {
      const merged: Record<string, unknown> = {...settings};
      const settingsPatch: Record<string, unknown> = {};
      for (const f of coreFields) {
        const v = (draft[f.key] ?? "").trim();
        if (v === "") continue;
        merged[f.key] = f.type === "number" ? Number(v) : v;
        if (f.productionInputKey) settingsPatch[f.productionInputKey] = merged[f.key];
        await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/decisions`, {
          stage: st.name,
          category: f.decision.category,
          subject: f.decision.subject,
          options_considered: f.options?.length ? f.options : [v],
          selected: v,
          reason: "flow 节点核心信息设置",
        });
      }
      if (Object.keys(settingsPatch).length > 0) {
        await patchJSON(`/api/project/${encodeURIComponent(state.project_id)}/settings`, {
          inputs: settingsPatch,
        });
      }
      onSettingsChange(merged);
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const saveProviderBar = async () => {
    if (!hasProviderBar) return;
    setBusy(true);
    setErr(null);
    try {
      const patch = providerBarPatch(providerBar, productionInputs);
      const merged: Record<string, unknown> = {...settings};
      const vp = providerBar.preferred_video_provider.trim();
      if (vp) merged.preferred_video_provider = vp;
      const selected = vp || "auto";
      await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/decisions`, {
        stage: st.name,
        category: "provider_selection",
        subject: "视频生成 Provider(preferred_video_provider)",
        options_considered: providerOptionsForDecision(videoProviders, selected),
        selected,
        reason: "flow Provider 工具条",
      });
      if (Object.keys(patch).length > 0) {
        await patchJSON(`/api/project/${encodeURIComponent(state.project_id)}/settings`, {inputs: patch});
      }
      onSettingsChange({...merged, ...patch});
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const flow = async () => {
    if (!runTarget) return;
    setBusy(true);
    setErr(null);
    try {
      await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/stage/run`, {
        stage: runTarget.name,
        parameters: stageRunParameters(settings),
      });
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    setBusy(true);
    setErr(null);
    try {
      await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/stage/approve`, {stage: st.name, notes: ""});
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (feedback.trim().length < 5) {
      setErr("驳回反馈至少 5 个字");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/stage/reject`, {
        stage: st.name,
        feedback: feedback.trim(),
      });
      setFeedback("");
      setRejecting(false);
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!activeRun) return;
    setBusy(true);
    setErr(null);
    try {
      await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/stage/run/${activeRun.task_id}/cancel`, {});
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const loadLogForRun = async (run: RunState, mode: "failure" | "full" = "full") => {
    setRunDetailsOpen(true);
    setBusy(true);
    setErr(null);
    try {
      const res = await getJSON(
        `/api/project/${encodeURIComponent(state.project_id)}/stage/run/${run.task_id}/log?offset=0&limit=2000`,
      );
      const lines = filterRunLogLines((res.lines ?? []) as string[], {mode});
      setLogText(lines.join("\n") || runLogHint || "（日志为空）");
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const openFailureDetails = async () => {
    setRunDetailsOpen(true);
    if (logRun?.task_id) {
      await loadLogForRun(logRun, "failure");
      return;
    }
    if (runLogHint) setLogText(runLogHint);
  };

  const loadLog = async () => {
    const run = activeRun ?? logRun;
    if (!run) return;
    await loadLogForRun(run, "full");
  };

  return (
    <div className="fs-ops" onClick={(e) => e.stopPropagation()}>
      <div className="fs-ops-head">
        <div className="fs-ops-title">
          <div className="fs-ops-title-row">
            {stageLabel(st.name)}
            <span className={`fs-badge fs-badge--${scls}`}>{railStatusLabel(st)}</span>
          </div>
          {st.status === "in_progress" && st.activity_hint && (
            <div className="fs-ops-activity">{st.activity_hint}</div>
          )}
        </div>

        <div className="fs-ops-actions">
          {st.status === "awaiting_human" && (
            <>
              <button className="fs-btn fs-btn--primary" onClick={approve} disabled={busy}>批准</button>
              <button className="fs-btn" onClick={() => setRejecting(!rejecting)} disabled={busy}>驳回</button>
            </>
          )}
          {st.status === "in_progress" && activeRun && (
            <button className="fs-btn" onClick={cancel} disabled={busy}>取消运行</button>
          )}
          {logRun?.task_id && (
            <button
              className="fs-btn"
              onClick={() => void (st.status === "failed" ? openFailureDetails() : loadLog())}
              disabled={busy}
            >
              {st.status === "failed" ? STRINGS.viewFailureDetails : STRINGS.viewRunLog}
            </button>
          )}
          {runTarget && (
            <button className="fs-btn fs-btn--primary" onClick={flow} disabled={busy} title={`运行: ${runTarget.name}`}>
              {runTarget.retry ? `↻ ${STRINGS.retry}` : `▶ 运行`} {runTarget.label}
            </button>
          )}
        </div>

        <button className="fs-btn fs-ops-close" onClick={onClose} aria-label="关闭">✕</button>
      </div>

      {rejecting && st.status === "awaiting_human" && (
        <div className="fs-ops-reject">
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="驳回原因(至少 5 个字)"
            rows={2}
          />
          <button className="fs-btn fs-btn--danger" onClick={reject} disabled={busy || feedback.trim().length < 5}>提交驳回</button>
          <button className="fs-btn" onClick={() => setRejecting(false)} disabled={busy}>取消</button>
        </div>
      )}

      {runDetailsOpen && st.status === "failed" && (
        <div className="fs-failed-banner">
          <div className="fs-failed-label">{STRINGS.failureReason}</div>
          <div className="fs-failed-text">{failureMsg || STRINGS.unknownFailure}</div>
          {logRun?.task_id && (
            <div className="fs-failed-meta">运行 {logRun.task_id.slice(0, 8)} · {logRun.status ?? "—"}</div>
          )}
        </div>
      )}

      {runDetailsOpen && logText && (
        <div className="fs-ops-log-wrap">
          <div className="fs-ops-log-label">
            {STRINGS.viewRunLog}
            {logRun?.task_id ? ` · ${logRun.task_id.slice(0, 8)}` : ""}
          </div>
          <pre className="fs-ops-log">{logText}</pre>
        </div>
      )}

      {err && <div className="fs-error">{err}</div>}

      <div className="fs-ops-content">
      {/* 输入(常驻顶部,不随 tab 切换):上个节点的输出 — 必需数据流 */}
      <div className="fs-input-top">
        <InputSlot state={state} stage={st} />
      </div>

      <div className="fs-ops-tabs">
        <button className={`fs-tab${tab === "see" ? " active" : ""}`} onClick={() => setTab("see")}>看</button>
        <button className={`fs-tab${tab === "edit" ? " active" : ""}`} onClick={() => setTab("edit")}>改</button>
      </div>

      <div className="fs-ops-body">
        {tab === "see" && (
          <div className="fs-see">
            {/* 本节点内容 */}
            <div className="fs-see-col">
              <div className="fs-section-title">{st.name === "compose" ? "合成输出" : "本节点内容"}</div>
              <OutputGrid state={state} stage={st} />
              <PreviewPane state={state} stage={st} playbookLabels={playbookLabels} />
            </div>
            {/* 参考素材:辅助参考,可追加 */}
            <ReferenceSlot
              state={state}
              extraRefs={extraRefs}
              onAddRef={(n) => setExtraRefs((r) => [...r, n])}
              onRemoveRef={(n) => setExtraRefs((r) => r.filter((x) => x !== n))}
            />
          </div>
        )}

        {tab === "edit" && (
          <div className="fs-edit">
            {coreFields.length === 0 && <div className="fs-muted">本阶段无可编辑的核心信息</div>}
            {coreFields.map((f) => (
              <div key={f.key} className="fs-core-field">
                <label>{f.label}</label>
                {f.type === "select" ? (
                  <>
                    <select value={draft[f.key] ?? ""} onChange={(e) => setDraft((d) => ({...d, [f.key]: e.target.value}))}>
                      <option value="">（未设置）</option>
                      {selectOptionsForField(f, videoProviders, playbookLabels).map((o) => (
                        <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
                      ))}
                    </select>
                    {f.dynamicOptions === "video_providers" && (
                      <p className="fs-field-hint">对应 video_selector 的 preferred_provider；未配置的项显示为灰色</p>
                    )}
                  </>
                ) : (
                  <input
                    type={f.type === "number" ? "number" : "text"}
                    value={draft[f.key] ?? ""}
                    onChange={(e) => setDraft((d) => ({...d, [f.key]: e.target.value}))}
                  />
                )}
              </div>
            ))}
            {coreFields.length > 0 && (
              <button className="fs-btn fs-btn--primary" onClick={saveCore} disabled={busy}>保存设置</button>
            )}
          </div>
        )}
      </div>
      </div>

      {hasProviderBar && (
        <ProviderToolbar
          values={providerBar}
          onChange={setProviderBar}
          videoProviders={videoProviders}
          onSave={saveProviderBar}
          busy={busy}
        />
      )}
    </div>
  );
}

// ---- 输入节点操作框:看(参考素材/参数)+ 改(production_inputs → PATCH /settings) ----
function InputOps({
  state,
  projectSettings,
  onClose,
  onChanged,
}: {
  state: BoardState;
  projectSettings: ProjectSettings | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<"see" | "edit">("see");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [videoProviders, setVideoProviders] = useState<VideoProviderOption[]>([]);
  const [providerBar, setProviderBar] = useState<ProviderBarValues>({
    preferred_video_provider: "",
    quality_tier: "",
    aspect_ratio: "",
    video_gen_clip_duration_seconds: "",
  });

  const inputs = projectSettings?.production_inputs ?? {};
  const sm = projectSettings?.source_media ?? state.source_media;
  const del = projectSettings?.deliverable ?? state.deliverable;
  const fields = projectSettings?.bootstrap_fields ?? {};

  // 可编辑字段:生产输入(排除 path 类；画质/比例/单段时长在底部 Provider 条)
  const EDITABLE = ["reference_url", "topic", "target_platform", "target_duration_seconds"];

  useEffect(() => {
    fetchVideoProviderOptions().then(setVideoProviders).catch(() => {});
  }, []);

  useEffect(() => {
    setProviderBar(providerBarFromInputs(inputs, del));
    const init: Record<string, string> = {};
    for (const key of EDITABLE) {
      const v = inputs[key];
      if (v != null) init[key] = String(v);
    }
    setDraft(init);
    setErr(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectSettings?.project_id]);

  const saveInputs = async () => {
    setBusy(true);
    setErr(null);
    try {
      const patch: Record<string, unknown> = {};
      for (const key of EDITABLE) {
        const v = (draft[key] ?? "").trim();
        if (v === "" && inputs[key] == null) continue;
        if (v === "" && inputs[key] != null) {
          patch[key] = null; // 清空
        } else {
          patch[key] = key.includes("duration") ? Number(v) : v;
        }
      }
      await patchJSON(`/api/project/${encodeURIComponent(state.project_id)}/settings`, {inputs: patch});
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const saveProvider = async () => {
    setBusy(true);
    setErr(null);
    try {
      const patch = providerBarPatch(providerBar, inputs);
      if (Object.keys(patch).length === 0) return;
      await patchJSON(`/api/project/${encodeURIComponent(state.project_id)}/settings`, {inputs: patch});
      onChanged();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const save = saveInputs;

  const playbackURL = sm?.path
    ? buildMediaURL(state.project_id, String(sm.path).replace(/^projects\/[^/]+\//, ""))
    : null;
  const posterURL = sm?.poster
    ? thumbURL(state.project_id, String(sm.poster), 320)
    : null;

  return (
    <div className="fs-ops" onClick={(e) => e.stopPropagation()}>
      <div className="fs-ops-head">
        <div className="fs-ops-title">
          <span className="fs-badge fs-badge--input">⏵ 输入</span>
          {projectSettings?.title ?? state.title ?? state.project_id}
        </div>
        <button className="fs-btn fs-ops-close" onClick={onClose} aria-label="关闭">✕</button>
      </div>

      {err && <div className="fs-error">{err}</div>}

      <div className="fs-ops-tabs">
        <button className={`fs-tab${tab === "see" ? " active" : ""}`} onClick={() => setTab("see")}>看</button>
        <button className={`fs-tab${tab === "edit" ? " active" : ""}`} onClick={() => setTab("edit")}>改</button>
      </div>

      <div className="fs-ops-body">
        {tab === "see" && (
          <div className="fs-see">
            <div className="fs-see-col">
              <div className="fs-section-title">参考素材</div>
              {posterURL && (
                <img
                  className="fs-input-poster-lg"
                  src={posterURL}
                  alt=""
                />
              )}
              {playbackURL && sm?.playable ? (
                <video className="fs-input-video" src={playbackURL} poster={posterURL || undefined} controls />
              ) : null}
              {typeof inputs.reference_url === "string" && inputs.reference_url && (
                <div className="fs-preview-row"><b>参考 URL</b>
                  <a className="fs-link" href={String(inputs.reference_url)} target="_blank" rel="noreferrer">{String(inputs.reference_url).slice(0, 60)}</a>
                </div>
              )}
              {sm?.summary && <div className="fs-preview-text">{String(sm.summary).slice(0, 300)}</div>}
              {!sm && !inputs.reference_url && <div className="fs-muted">尚未录入参考素材(可在「改」中填写 URL 或话题)</div>}
            </div>
            <div className="fs-see-col">
              <div className="fs-section-title">需求参数(输入)</div>
              <div className="fs-preview-row"><b>目标平台</b>{inputs.target_platform != null ? String(inputs.target_platform) : "—"}</div>
              <div className="fs-preview-row"><b>目标时长</b>{inputs.target_duration_seconds != null ? `${String(inputs.target_duration_seconds)}s` : "—"}</div>
              <div className="fs-preview-row"><b>画质</b>{inputs.quality_tier != null ? String(inputs.quality_tier) : del?.quality_tier ?? "—"}</div>
              <div className="fs-preview-row"><b>画幅</b>{inputs.aspect_ratio != null ? String(inputs.aspect_ratio) : del?.aspect_ratio ?? "—"}</div>
              <div className="fs-preview-row"><b>单段时长</b>{inputs.video_gen_clip_duration_seconds != null ? `${String(inputs.video_gen_clip_duration_seconds)}s` : "—"}</div>
              <div className="fs-preview-row"><b>视频 Provider</b>{inputs.preferred_video_provider ? optionLabel("preferred_video_provider", String(inputs.preferred_video_provider)) : "自动"}</div>
              {typeof inputs.topic === "string" && inputs.topic && (
                <div className="fs-preview-block">
                  <div className="fs-preview-label">话题</div>
                  <div className="fs-preview-text">{String(inputs.topic).slice(0, 200)}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "edit" && (
          <div className="fs-edit">
            {EDITABLE.filter((k) => fields[k] || ["reference_url", "topic", "target_platform", "target_duration_seconds"].includes(k)).map((key) => {
              const schema = fields[key] ?? {};
              const opts = Array.isArray(schema.options) ? schema.options : undefined;
              return (
                <div key={key} className="fs-core-field">
                  <label>{String(schema.label ?? key)}</label>
                  {opts && opts.length > 0 ? (
                    <select value={draft[key] ?? ""} onChange={(e) => setDraft((d) => ({...d, [key]: e.target.value}))}>
                      <option value="">（未设置）</option>
                      {opts.map((o) => (
                        <option key={String(o)} value={String(o)}>{String(o)}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={key.includes("duration") ? "number" : "text"}
                      value={draft[key] ?? ""}
                      onChange={(e) => setDraft((d) => ({...d, [key]: e.target.value}))}
                      placeholder={String(schema.label ?? key)}
                    />
                  )}
                </div>
              );
            })}
            <button className="fs-btn fs-btn--primary" onClick={save} disabled={busy}>保存输入设置</button>
          </div>
        )}
      </div>

      <ProviderToolbar
        values={providerBar}
        onChange={setProviderBar}
        videoProviders={videoProviders}
        onSave={saveProvider}
        busy={busy}
      />
    </div>
  );
}
