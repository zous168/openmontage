import type {BoardState, RunState, StageState} from "./types";

export function latestRunForStage(state: BoardState, stageName: string): RunState | undefined {
  return (state.runs ?? []).find((r) => r.stage === stageName);
}

export function failedRunForStage(state: BoardState, stageName: string): RunState | undefined {
  return (state.runs ?? []).find((r) => r.stage === stageName && r.status === "failed");
}

export function extractAgentRunSummary(log: string): string | null {
  const m = log.match(/agent_run_summary:\s*(.+?)(?:\n|$)/i);
  return m?.[1]?.trim() ?? null;
}

/** 失败原因：优先 checkpoint.error，其次 run 摘要，最后才是 partial_progress 短提示 */
export function failureMessage(stage: StageState, state: BoardState): string | null {
  if (stage.status !== "failed") return null;
  const fromCheckpoint = stage.error?.trim();
  if (fromCheckpoint) return fromCheckpoint;

  const run = latestRunForStage(state, stage.name) ?? failedRunForStage(state, stage.name);
  if (run?.error?.trim()) return run.error.trim();
  if (run?.log_tail?.trim()) {
    const summary = extractAgentRunSummary(run.log_tail);
    if (summary) return summary;
  }

  if (run?.log_tail?.trim()) return run.log_tail.trim().slice(-400);
  if (run?.exit_code != null && run.exit_code !== 0) return `agent 退出码 ${run.exit_code}`;
  return null;
}

/** 运行日志预览：过滤掉 agent 列目录时的纯路径行 */
export function filterRunLogLines(lines: string[]): string[] {
  const trimmed = lines.map((l) => l.trim()).filter(Boolean);
  const interesting = trimmed.filter((l) =>
    /agent_run_summary|error|failed|provider|不可用|Exception|traceback|video_generation/i.test(l),
  );
  if (interesting.length >= 2) return interesting.slice(-40);
  const sansPaths = trimmed.filter((l) => !/^projects[\\/][\w.-]+[\\/][\w\\/.-]+\.(json|log|mp4|md)$/i.test(l));
  return (sansPaths.length > 0 ? sansPaths : trimmed).slice(-35);
}

export function runLogPreview(run: RunState | undefined): string | null {
  if (!run?.log_tail?.trim()) return null;
  const summary = extractAgentRunSummary(run.log_tail);
  if (summary) return summary;
  const lines = run.log_tail.split("\n");
  const filtered = filterRunLogLines(lines);
  return filtered.join("\n") || run.log_tail.trim().slice(-400);
}
