import type { Translations } from "@/i18n/types";

/** Keys must match `_AUX_TASK_SLOTS` in hermes_cli/web_server.py. */
export const AUX_TASK_KEYS = [
  "vision",
  "web_extract",
  "compression",
  "skills_hub",
  "approval",
  "mcp",
  "title_generation",
  "triage_specifier",
  "kanban_decomposer",
  "profile_describer",
  "curator",
] as const;

export type AuxTaskKey = (typeof AUX_TASK_KEYS)[number];

const FALLBACK: Record<AuxTaskKey, { label: string; hint: string }> = {
  vision: { label: "Vision", hint: "Image analysis" },
  web_extract: { label: "Web Extract", hint: "Page summarization" },
  compression: { label: "Compression", hint: "Context compaction" },
  skills_hub: { label: "Skills Hub", hint: "Skill search" },
  approval: { label: "Approval", hint: "Smart auto-approve" },
  mcp: { label: "MCP", hint: "MCP tool routing" },
  title_generation: { label: "Title Gen", hint: "Session titles" },
  triage_specifier: { label: "Triage Specifier", hint: "Kanban spec fleshing" },
  kanban_decomposer: { label: "Kanban Decomposer", hint: "Task decomposition" },
  profile_describer: { label: "Profile Describer", hint: "Auto profile descriptions" },
  curator: { label: "Curator", hint: "Skill-usage review" },
};

export function resolveAuxTasks(t: Translations) {
  return AUX_TASK_KEYS.map((key) => {
    const localized = t.models2?.auxTasks?.[key];
    const fb = FALLBACK[key];
    return {
      key,
      label: localized?.label ?? fb.label,
      hint: localized?.hint ?? fb.hint,
    };
  });
}

export function auxTaskLabel(taskKey: string, t: Translations): string {
  return t.models2?.auxTasks?.[taskKey]?.label ?? FALLBACK[taskKey as AuxTaskKey]?.label ?? taskKey;
}
