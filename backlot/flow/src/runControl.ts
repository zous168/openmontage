import type {BoardState, StageState} from "./types";
import {postJSON} from "./api";

function activeRun(state: BoardState) {
  return state.runs?.find((r) => r.status === "queued" || r.status === "running");
}

/** 与 board.js pendingAutoRunStage 对齐 */
export function pendingAutoRunStage(state: BoardState): StageState | null {
  if (activeRun(state)) return null;
  if (state.stages?.some((s) => s.status === "awaiting_human")) return null;
  const nextName = state.next_stage;
  if (!nextName) return null;
  const next = state.stages?.find((s) => s.name === nextName);
  if (!next || next.status !== "pending") return null;
  const idx = state.stages!.findIndex((s) => s.name === nextName);
  const prev = idx > 0 ? state.stages![idx - 1] : null;
  if (!prev || prev.status !== "completed") return null;
  return next;
}

let autoRunInFlight = false;

/** SSE/批准后若下一阶段仍 pending，自动 POST stage/run（服务端也会 chain，此处作兜底） */
export async function maybeAutoRunNextStage(
  state: BoardState,
  onChanged: () => void | Promise<void>,
): Promise<void> {
  const next = pendingAutoRunStage(state);
  if (!next || autoRunInFlight || !state.project_id) return;
  autoRunInFlight = true;
  try {
    await postJSON(`/api/project/${encodeURIComponent(state.project_id)}/stage/run`, {
      stage: next.name,
    });
    await onChanged();
  } catch {
    await onChanged();
  } finally {
    autoRunInFlight = false;
  }
}
