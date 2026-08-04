import type {BoardState} from "./types";
import {stageLabel, statusLabel} from "./labels";

export interface PipelineProgress {
  total: number;
  completed: number;
  failed: number;
  pct: number;
  running: {name: string; label: string} | null;
  awaiting: {name: string; label: string} | null;
  next: {name: string; label: string} | null;
  summary: string;
}

export function pipelineProgress(state: BoardState): PipelineProgress {
  const stages = (state.stages ?? []).filter((s) => !s.undeclared);
  const total = stages.length;
  const completed = stages.filter((s) => s.status === "completed").length;
  const failed = stages.filter((s) => s.status === "failed").length;
  const runningSt = stages.find((s) => s.status === "in_progress");
  const awaitingSt = stages.find((s) => s.status === "awaiting_human");
  const nextSt = stages.find((s) => s.is_next && s.status === "pending") ?? null;

  const running = runningSt ? {name: runningSt.name, label: stageLabel(runningSt.name)} : null;
  const awaiting = awaitingSt ? {name: awaitingSt.name, label: stageLabel(awaitingSt.name)} : null;
  const next = nextSt ? {name: nextSt.name, label: stageLabel(nextSt.name)} : null;

  let summary = `${completed}/${total} ${statusLabel("completed")}`;
  if (running) summary += ` · ${running.label} ${statusLabel("in_progress")}`;
  else if (awaiting) summary += ` · ${awaiting.label} ${statusLabel("awaiting_human")}`;
  else if (next) summary += ` · ${next.label} ${statusLabel("pendingNext")}`;
  else if (failed > 0) summary += ` · ${failed} ${statusLabel("failed")}`;

  return {
    total,
    completed,
    failed,
    pct: total > 0 ? Math.round((completed / total) * 100) : 0,
    running,
    awaiting,
    next,
    summary,
  };
}

export function FlowProgressBar({state}: {state: BoardState}) {
  const p = pipelineProgress(state);
  if (p.total <= 0) return null;

  return (
    <div className="fs-progress" role="status" aria-live="polite">
      <div className="fs-progress-track" aria-hidden>
        <div className="fs-progress-fill" style={{width: `${p.pct}%`}} />
        {p.running && <div className="fs-progress-active" />}
      </div>
      <span className="fs-progress-text">{p.summary}</span>
    </div>
  );
}
