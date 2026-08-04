// 底部操作框(RunHub 式):选中节点 → 画布底部浮出。
// 看:本节点内容预览 + 参考槽 | 改:核心信息表单
// 批准/运行/日志等操作在标题栏右侧(无「做」Tab)
import {useEffect, useMemo, useState} from "react";
import type {BoardState, ProjectSettings, RunState, StageState} from "./types";
import {artifactLabel, railStatusLabel, stageLabel, STRINGS} from "./labels";
import {stageOutputs, upstreamArtifacts, statusCls} from "./graph";
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
    const outs = (art as {outputs?: {path?: string; format?: string; resolution?: string}[]}).outputs ?? [];
    return (
      <div className="fs-preview">
        {outs.map((o, i) => (
          <div key={i} className="fs-preview-row">
            <b>输出 {i + 1}</b> {String(o.format ?? "")} · {String(o.resolution ?? "")} —{" "}
            <a className="fs-link" href={`/media/${encodeURIComponent(state.project_id)}/${String(o.path ?? "").replace(/^projects\/[^/]+\//, "")}`} target="_blank" rel="noreferrer">
              {String(o.path ?? "").split("/").pop()}
            </a>
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

// ---- 看区:参考槽(上游产物卡片 + 会话级追加) ----
function ReferenceSlot({
  state, stage, extraRefs, onAddRef, onRemoveRef,
}: {
  state: BoardState;
  stage: StageState;
  extraRefs: string[];
  onAddRef: (name: string) => void;
  onRemoveRef: (name: string) => void;
}) {
  const upstream = upstreamArtifacts(state, stage);
  const arts = state.artifacts ?? {};
  const [picking, setPicking] = useState(false);
  const available = Object.keys(arts).filter(
    (n) => !upstream.some((u) => u.name === n) && !extraRefs.includes(n) && n !== "decision_log",
  );

  return (
    <div className="fs-refs">
      <div className="fs-refs-label">参考槽 · 上游已绑定</div>
      <div className="fs-refs-grid">
        {upstream.map((u) => (
          <RefCard key={u.name} name={u.name} value={u.value} projectId={state.project_id} removable={false} onRemove={() => {}} />
        ))}
        {extraRefs.map((n) => (
          <RefCard key={n} name={n} value={arts[n]} projectId={state.project_id} removable onRemove={() => onRemoveRef(n)} />
        ))}
        {upstream.length === 0 && extraRefs.length === 0 && (
          <div className="fs-muted">暂无上游产物(前置阶段完成后自动出现)</div>
        )}
      </div>
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

function RefCard({
  name, value, projectId, removable, onRemove,
}: {
  name: string;
  value: unknown;
  projectId: string;
  removable: boolean;
  onRemove: () => void;
}) {
  const [thumb, setThumb] = useState<string | null>(null);
  const path = useMemo(() => {
    if (value && typeof value === "object" && "path" in (value as Record<string, unknown>)) {
      return String((value as Record<string, unknown>).path).replace(/^projects\/[^/]+\//, "");
    }
    if (Array.isArray(value) && value.length > 0 && value[0] && typeof value[0] === "object" && "path" in value[0]) {
      return String((value[0] as Record<string, unknown>).path).replace(/^projects\/[^/]+\//, "");
    }
    return null;
  }, [value]);

  useEffect(() => {
    if (!path) return;
    const lower = path.toLowerCase();
    if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".webp")) {
      setThumb(`/thumb/${encodeURIComponent(projectId)}/${encodeURIComponent(path)}?w=240`);
    } else {
      setThumb(null);
    }
  }, [path, projectId]);

  const summary = useMemo(() => {
    if (typeof value === "string") return value.slice(0, 120);
    if (value && typeof value === "object") {
      const text = JSON.stringify(value);
      return text.length > 120 ? text.slice(0, 120) + "…" : text;
    }
    return String(value ?? "");
  }, [value]);

  return (
    <div className="fs-ref-card">
      {thumb && <img className="fs-ref-thumb" src={thumb} alt={name} />}
      <div className="fs-ref-body">
        <div className="fs-ref-name">{artifactLabel(name)}</div>
        <div className="fs-ref-summary">{thumb ? "" : summary}</div>
        {path && (
          <a className="fs-link fs-ref-link" href={`/media/${encodeURIComponent(projectId)}/${encodeURIComponent(path)}`} target="_blank" rel="noreferrer">
            打开
          </a>
        )}
      </div>
      {removable && <button className="fs-ref-x" onClick={onRemove} title="移除参考">✕</button>}
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
  const activeRun = state.runs?.find((r) => r.task_id === st.active_run_id);
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

  const loadLogForRun = async (run: RunState) => {
    setRunDetailsOpen(true);
    setBusy(true);
    setErr(null);
    try {
      const res = await getJSON(
        `/api/project/${encodeURIComponent(state.project_id)}/stage/run/${run.task_id}/log?offset=0&limit=2000`,
      );
      const lines = filterRunLogLines((res.lines ?? []) as string[]);
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
      await loadLogForRun(logRun);
      return;
    }
    if (runLogHint) setLogText(runLogHint);
  };

  const loadLog = async () => {
    if (!activeRun) return;
    await loadLogForRun(activeRun);
  };

  return (
    <div className="fs-ops" onClick={(e) => e.stopPropagation()}>
      <div className="fs-ops-head">
        <div className="fs-ops-title">
          {stageLabel(st.name)}
          <span className={`fs-badge fs-badge--${scls}`}>{railStatusLabel(st)}</span>
        </div>

        <div className="fs-ops-actions">
          {st.status === "awaiting_human" && (
            <>
              <button className="fs-btn fs-btn--primary" onClick={approve} disabled={busy}>批准</button>
              <button className="fs-btn" onClick={() => setRejecting(!rejecting)} disabled={busy}>驳回</button>
            </>
          )}
          {st.status === "in_progress" && activeRun && (
            <>
              <button className="fs-btn" onClick={cancel} disabled={busy}>取消运行</button>
              <button className="fs-btn" onClick={loadLog} disabled={busy}>运行日志</button>
            </>
          )}
          {st.status === "failed" && (
            <button className="fs-btn" onClick={() => void openFailureDetails()} disabled={busy}>
              {STRINGS.viewFailureDetails}
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
          <div className="fs-ops-log-label">运行日志</div>
          <pre className="fs-ops-log">{logText}</pre>
        </div>
      )}

      {err && <div className="fs-error">{err}</div>}

      <div className="fs-ops-tabs">
        <button className={`fs-tab${tab === "see" ? " active" : ""}`} onClick={() => setTab("see")}>看</button>
        <button className={`fs-tab${tab === "edit" ? " active" : ""}`} onClick={() => setTab("edit")}>改</button>
      </div>

      <div className="fs-ops-body">
        {tab === "see" && (
          <div className="fs-see">
            <div className="fs-see-col">
              <div className="fs-section-title">本节点内容</div>
              <PreviewPane state={state} stage={st} playbookLabels={playbookLabels} />
            </div>
            <div className="fs-see-col">
              <ReferenceSlot
                state={state}
                stage={st}
                extraRefs={extraRefs}
                onAddRef={(n) => setExtraRefs((r) => [...r, n])}
                onRemoveRef={(n) => setExtraRefs((r) => r.filter((x) => x !== n))}
              />
            </div>
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

  const mediaURL = sm?.path ? `/media/${encodeURIComponent(state.project_id)}/${encodeURIComponent(String(sm.path).replace(/^projects\/[^/]+\//, ""))}` : null;

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
              {sm?.poster && (
                <img
                  className="fs-input-poster-lg"
                  src={`/thumb/${encodeURIComponent(state.project_id)}/${encodeURIComponent(String(sm.poster))}?w=320`}
                  alt=""
                />
              )}
              {mediaURL && sm?.playable ? (
                <video className="fs-input-video" src={mediaURL} poster={sm?.poster ? `/thumb/${encodeURIComponent(state.project_id)}/${encodeURIComponent(String(sm.poster))}?w=320` : undefined} controls />
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
