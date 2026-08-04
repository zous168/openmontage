// BoardState 子集类型 — 只声明 flow 视图消费的字段(来自 GET /api/project/{id}/state)

export type StageStatus =
  | "pending"
  | "completed"
  | "awaiting_human"
  | "in_progress"
  | "failed";

export interface HistoryEntry {
  status: string;
  timestamp: string;
}

export interface StageState {
  name: string;
  gated?: boolean;
  produces?: string[];
  status: StageStatus;
  timestamp?: string | null;
  human_approved?: boolean | null;
  error?: string | null;
  partial_progress?: string | {completed_scene_ids?: string[]} | null;
  versions?: number;
  history_entries?: HistoryEntry[];
  gate_skipped?: boolean;
  blocked_by_upstream?: boolean;
  inferred_from_events?: boolean;
  inferred_from_run?: boolean;
  active_run_id?: string | null;
  is_next?: boolean;
  stalled?: boolean;
  stalled_minutes?: number;
  undeclared?: boolean;
  outputs?: string[];
}

export interface PipelineStageMeta {
  name: string;
  gated?: boolean;
  produces?: string[];
}

export interface RunState {
  task_id: string;
  stage: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
  error?: string | null;
  log_tail?: string | null;
}

export interface PipelineMeta {
  pipeline_type?: string;
  label_zh?: string;
  stages?: PipelineStageMeta[];
  known?: boolean;
}

export interface BoardState {
  project_id: string;
  title?: string;
  pipeline?: PipelineMeta;
  stages?: StageState[];
  runs?: RunState[];
  artifacts?: Record<string, unknown>;
  next_stage?: string | null;
  live?: boolean;
  has_pipeline_state?: boolean;
  cost?: {total_spent_usd?: number; budget_remaining_usd?: number} | null;
  source_media?: SourceMedia | null;
  deliverable?: Deliverable | null;
  poster?: string | null;
}

// ---- 输入节点数据(来自 /state 与 /settings) ----

export interface SourceMedia {
  kind?: string;
  path?: string;
  exists?: boolean;
  playable?: boolean;
  playback_path?: string | null;
  poster?: string | null;
  preview_path?: string | null;
  summary?: string;
  duration_seconds?: unknown;
  resolution?: unknown;
  format?: unknown;
  codec?: unknown;
}

export interface Deliverable {
  target_platform?: string;
  aspect_ratio?: string;
  quality_tier?: string;
  fps?: number;
  width?: number;
  height?: number;
  resolution?: string;
  media_profile?: string;
}

export interface ProductionInputs {
  [key: string]: unknown;
  reference_url?: string;
  topic?: string;
  target_platform?: string;
  target_duration_seconds?: number;
  preferred_video_provider?: string;
  source_media_path?: string;
  reference_media_path?: string;
}

export interface ProjectSettings {
  project_id?: string;
  title?: string;
  pipeline_type?: string;
  style_playbook?: string | null;
  bootstrap_notes?: string;
  production_inputs?: ProductionInputs;
  deliverable?: Deliverable | null;
  source_media?: SourceMedia | null;
  cover_brief?: unknown;
  has_pipeline_state?: boolean;
  bootstrap_fields?: Record<string, {label?: string; type?: string; options?: string[]; locked?: boolean}>;
}
