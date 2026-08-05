import { useCallback, useEffect, useState } from "react";
import { Clock, History, Pause, Pencil, Play, Trash2, X, Zap } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { api } from "@/lib/api";
import type { CronJob, CronDeliveryTarget, CronJobOutput, ProfileInfo, SkillInfo } from "@/lib/api";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import {
  DEFAULT_SCHEDULE_STATE,
  ScheduleBuilder,
} from "@/components/ScheduleBuilder";
import {
  buildScheduleString,
  describeSchedule,
  englishOrdinal,
  parseScheduleToState,
  type ScheduleBuilderState,
  type ScheduleDescribeStrings,
} from "@/lib/schedule";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { PluginSlot } from "@/plugins";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { AutomationBlueprints } from "@/components/AutomationBlueprints";
import { cn, themedBody } from "@/lib/utils";

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function truncateText(value: string, maxLength: number): string {
  return value.length > maxLength
    ? value.slice(0, maxLength) + "..."
    : value;
}

function getJobPrompt(job: CronJob): string {
  return asText(job.prompt);
}

/** Compact multi-select for attaching skills to a cron job.
 *
 * A checkbox list (native inputs — the `onValueChange` rule is Select-only)
 * capped to a scrollable box. Skills already on the job but missing from the
 * available list (e.g. removed from disk, or the job was created via CLI in
 * another profile) are still rendered so saving doesn't silently drop them.
 */
function SkillsPicker({
  id,
  available,
  selected,
  onChange,
  emptyLabel,
}: {
  id: string;
  available: SkillInfo[];
  selected: string[];
  onChange: (skills: string[]) => void;
  emptyLabel: string;
}) {
  const names = available.map((s) => s.name);
  const orphaned = selected.filter((s) => !names.includes(s));
  const all = [...orphaned.map((name) => ({ name, description: "" })), ...available];

  if (all.length === 0) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }

  const toggle = (name: string, checked: boolean) => {
    if (checked) onChange([...selected, name]);
    else onChange(selected.filter((s) => s !== name));
  };

  return (
    <div
      id={id}
      className="max-h-36 overflow-y-auto border border-border bg-background/40 p-1"
    >
      {all.map((skill) => (
        <label
          key={skill.name}
          className="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs hover:bg-muted/40"
          title={skill.description || undefined}
        >
          <input
            type="checkbox"
            className="accent-foreground"
            checked={selected.includes(skill.name)}
            onChange={(e) => toggle(skill.name, e.target.checked)}
          />
          <span className="font-mono-ui truncate">{skill.name}</span>
        </label>
      ))}
    </div>
  );
}

function getJobName(job: CronJob): string {
  return asText(job.name).trim();
}

function getJobTitle(job: CronJob): string {
  const name = getJobName(job);
  if (name) return name;

  const prompt = getJobPrompt(job);
  if (prompt) return truncateText(prompt, 60);

  const script = asText(job.script);
  if (script) return truncateText(script, 60);

  return job.id || "Cron job";
}

type CronExecutionMode = "agent" | "script_agent" | "no_agent" | "http";

function inferExecutionMode(job: Pick<CronJob, "no_agent" | "script" | "http">): CronExecutionMode {
  if (job.http) return "http";
  if (job.no_agent) return "no_agent";
  if (job.script) return "script_agent";
  return "agent";
}

function modeUsesScript(mode: CronExecutionMode): boolean {
  return mode === "no_agent" || mode === "script_agent";
}

// http 执行类型的表单原始字符串（url/method/timeout 单行，headers 多行 "Key: Value"，body 原文）。
type CronHttpForm = {
  url: string;
  method: string;
  headers: string;
  timeout: string;
  body: string;
};

const EMPTY_HTTP_FORM: CronHttpForm = {
  url: "",
  method: "POST",
  headers: "",
  timeout: "",
  body: "",
};

function parseHeaderLines(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const idx = trimmed.indexOf(":");
    if (idx <= 0) continue;
    const key = trimmed.slice(0, idx).trim();
    if (key) out[key] = trimmed.slice(idx + 1).trim();
  }
  return out;
}

function stringifyHeaders(headers?: Record<string, string> | null): string {
  if (!headers) return "";
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
}

function httpFormFromJob(job: Pick<CronJob, "http">): CronHttpForm {
  const http = job.http;
  if (!http) return { ...EMPTY_HTTP_FORM };
  const rawBody = http.body;
  return {
    url: http.url ?? "",
    method: http.method ?? "POST",
    headers: stringifyHeaders(http.headers),
    timeout: http.timeout != null ? String(http.timeout) : "",
    body:
      rawBody == null
        ? ""
        : typeof rawBody === "string"
          ? rawBody
          : JSON.stringify(rawBody, null, 2),
  };
}

function buildCronExecutionPayload(
  mode: CronExecutionMode,
  prompt: string,
  script: string,
  skills: string[],
  http: CronHttpForm,
): {
  prompt?: string;
  script?: string | null;
  no_agent?: boolean;
  skills?: string[];
  http?: {
    url: string;
    method: string;
    headers?: Record<string, string>;
    timeout?: number;
    body?: string;
  } | null;
} {
  if (mode === "http") {
    const headers = parseHeaderLines(http.headers);
    const timeoutNum = http.timeout.trim() ? Number(http.timeout.trim()) : NaN;
    const bodyText = http.body.trim();
    // http 是通用一等执行类型：一并清空 agent/script 字段，避免切换模式后残留旧 prompt/script。
    return {
      http: {
        url: http.url.trim(),
        method: (http.method || "POST").toUpperCase(),
        headers: Object.keys(headers).length > 0 ? headers : undefined,
        timeout: Number.isFinite(timeoutNum) ? timeoutNum : undefined,
        body: bodyText || undefined,
      },
      prompt: "",
      script: null,
      no_agent: false,
    };
  }
  const trimmedPrompt = prompt.trim();
  const trimmedScript = script.trim();
  if (mode === "no_agent") {
    return {
      prompt: trimmedPrompt || trimmedScript,
      script: trimmedScript,
      no_agent: true,
      http: null,
    };
  }
  if (mode === "script_agent") {
    return {
      prompt: trimmedPrompt,
      script: trimmedScript || undefined,
      no_agent: false,
      skills: skills.length > 0 ? skills : undefined,
      http: null,
    };
  }
  return {
    prompt: trimmedPrompt,
    no_agent: false,
    script: null,
    skills: skills.length > 0 ? skills : undefined,
    http: null,
  };
}

function validateCronExecution(
  mode: CronExecutionMode,
  prompt: string,
  script: string,
  skills: string[],
  http: CronHttpForm,
  messages: { scriptRequired: string; promptOrSkillsRequired: string; httpUrlRequired: string },
): string | null {
  if (mode === "http") {
    if (!http.url.trim()) return messages.httpUrlRequired;
    return null;
  }
  const trimmedPrompt = prompt.trim();
  const trimmedScript = script.trim();
  if (mode === "no_agent") {
    if (!trimmedScript) return messages.scriptRequired;
    return null;
  }
  if (mode === "script_agent") {
    if (!trimmedScript) return messages.scriptRequired;
    if (!trimmedPrompt && skills.length === 0) return messages.promptOrSkillsRequired;
    return null;
  }
  if (!trimmedPrompt && skills.length === 0) return messages.promptOrSkillsRequired;
  return null;
}

const HTTP_METHODS = ["POST", "GET", "PUT", "PATCH", "DELETE"] as const;

// http 执行类型的通用表单（create/edit 弹窗共用）：URL / 方法 / 超时 / 请求头。
function CronHttpFields({
  idPrefix,
  form,
  onChange,
  t,
}: {
  idPrefix: string;
  form: CronHttpForm;
  onChange: (next: CronHttpForm) => void;
  t: Translations;
}) {
  return (
    <>
      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-http-url`}>{t.cron.httpUrl ?? "Request URL"}</Label>
        <Input
          id={`${idPrefix}-http-url`}
          placeholder={t.cron.httpUrlPlaceholder ?? "https://host/api/endpoint"}
          value={form.url}
          onChange={(e) => onChange({ ...form, url: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label htmlFor={`${idPrefix}-http-method`}>{t.cron.httpMethod ?? "Method"}</Label>
          <Select
            id={`${idPrefix}-http-method`}
            value={form.method || "POST"}
            onValueChange={(v) => onChange({ ...form, method: v })}
          >
            {HTTP_METHODS.map((m) => (
              <SelectOption key={m} value={m}>
                {m}
              </SelectOption>
            ))}
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${idPrefix}-http-timeout`}>{t.cron.httpTimeout ?? "Timeout (s)"}</Label>
          <Input
            id={`${idPrefix}-http-timeout`}
            type="number"
            placeholder="120"
            value={form.timeout}
            onChange={(e) => onChange({ ...form, timeout: e.target.value })}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-http-headers`}>{t.cron.httpHeaders ?? "Headers"}</Label>
        <textarea
          id={`${idPrefix}-http-headers`}
          className="flex min-h-[60px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
          placeholder={"Authorization: Bearer xxx"}
          value={form.headers}
          onChange={(e) => onChange({ ...form, headers: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          {t.cron.httpHeadersHint ?? 'One header per line, formatted as "Key: Value".'}
        </p>
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${idPrefix}-http-body`}>{t.cron.httpBody ?? "Request body"}</Label>
        <textarea
          id={`${idPrefix}-http-body`}
          className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
          placeholder={'{"key": "value"}'}
          value={form.body}
          onChange={(e) => onChange({ ...form, body: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          {t.cron.httpBodyHint ??
            "Sent as-is (Content-Type from headers). JSON is typical for POST/PUT."}
        </p>
      </div>
      <p className="text-xs text-muted-foreground">
        {t.cron.httpPlaceholderHint ??
          "Placeholders expand at run time: {cronId}, {cronName}, {env.VAR} (e.g. {env.API_SERVER_KEY}) — secrets are never stored."}
      </p>
    </>
  );
}

function getJobScheduleDisplay(
  job: CronJob,
  strings: ScheduleDescribeStrings,
): string {
  // Prefer a structured render so cron expressions like
  // ``30 14 * * 1,3,5`` surface as "Weekly on Mon, Wed, Fri at 14:30"
  // in the list instead of the raw five-field gibberish. Falls back
  // through the existing chain (``schedule_display`` from the backend,
  // then the structured ``display`` field, then the raw ``expr``) so
  // legacy job rows still render *something* meaningful.
  return describeSchedule(
    job.schedule,
    asText(job.schedule_display) || asText(job.schedule?.display),
    strings,
  );
}

function getJobState(job: CronJob): string {
  return asText(job.state) || (job.enabled === false ? "disabled" : "scheduled");
}

function getJobProfile(job: CronJob): string {
  return asText(job.profile) || asText(job.profile_name) || "default";
}

function getJobKey(job: CronJob): string {
  return `${getJobProfile(job)}:${job.id}`;
}

function splitJobKey(key: string): { profile: string; id: string } {
  const idx = key.indexOf(":");
  if (idx === -1) return { profile: "default", id: key };
  return { profile: key.slice(0, idx) || "default", id: key.slice(idx + 1) };
}

function profileLabel(profile: string): string {
  return profile === "default" ? "default" : profile;
}

const STATUS_TONE: Record<string, "success" | "warning" | "destructive"> = {
  enabled: "success",
  scheduled: "success",
  paused: "warning",
  error: "destructive",
  completed: "destructive",
};

export default function CronPage() {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [selectedProfile, setSelectedProfile] = useState("all");
  const [view, setView] = useState<"jobs" | "blueprints">("jobs");
  const [loading, setLoading] = useState(true);
  const { toast, showToast } = useToast();
  const { t, locale } = useI18n();

  // Translation surface for the human-readable schedule describer.
  // English ordinals are a special case ("1st", "2nd", "23rd"); every
  // other locale falls back to the plain numeric form, which avoids
  // shipping incorrect grammar (e.g. naive "1th"/"2th" suffixes that
  // don't exist in most languages).
  //
  // Built inline (not memoized) — the cron page renders a small job
  // list, this is single-digit microseconds, and a useMemo here would
  // just add boilerplate.
  const scheduleDescribeStrings: ScheduleDescribeStrings = {
    ...t.cron.scheduleDescribe,
    weekdaysShort: t.cron.scheduleModes.weekdaysShort,
    ordinal: locale === "en" ? englishOrdinal : (n: number) => String(n),
  };

  // New job modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  // The schedule is now constructed via the ScheduleBuilder; we keep
  // the full builder state so flipping between modes during edit
  // doesn't erase the user's intermediate inputs. The actual string
  // sent to the backend is derived via ``buildScheduleString`` at
  // submit time.
  const [scheduleState, setScheduleState] = useState<ScheduleBuilderState>(
    DEFAULT_SCHEDULE_STATE,
  );
  const [name, setName] = useState("");
  const closeCreateModal = useCallback(() => setCreateModalOpen(false), []);
  const createModalRef = useModalBehavior({
    open: createModalOpen,
    onClose: closeCreateModal,
  });
  const [deliver, setDeliver] = useState("local");
  const [jobSkills, setJobSkills] = useState<string[]>([]);
  const [executionMode, setExecutionMode] = useState<CronExecutionMode>("agent");
  const [script, setScript] = useState("");
  const [httpForm, setHttpForm] = useState<CronHttpForm>({ ...EMPTY_HTTP_FORM });
  const [deliveryTargets, setDeliveryTargets] = useState<CronDeliveryTarget[]>([
    { id: "local", name: "Local", home_target_set: true, home_env_var: null },
  ]);
  const [creating, setCreating] = useState(false);
  const createProfile = selectedProfile === "all" ? "default" : selectedProfile;

  // Edit job modal state
  const [editJob, setEditJob] = useState<CronJob | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [editScheduleState, setEditScheduleState] = useState<ScheduleBuilderState>(DEFAULT_SCHEDULE_STATE);
  const [editName, setEditName] = useState("");
  const [editDeliver, setEditDeliver] = useState("local");
  const [editSkills, setEditSkills] = useState<string[]>([]);
  const [editExecutionMode, setEditExecutionMode] = useState<CronExecutionMode>("agent");
  const [editScript, setEditScript] = useState("");
  const [editHttpForm, setEditHttpForm] = useState<CronHttpForm>({ ...EMPTY_HTTP_FORM });
  const [saving, setSaving] = useState(false);
  const closeEditModal = useCallback(() => setEditJob(null), []);
  const editModalRef = useModalBehavior({
    open: editJob !== null,
    onClose: closeEditModal,
  });

  const [runsJob, setRunsJob] = useState<CronJob | null>(null);
  const [runOutputs, setRunOutputs] = useState<CronJobOutput[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [selectedRun, setSelectedRun] = useState<CronJobOutput | null>(null);
  const [runDetail, setRunDetail] = useState("");
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const closeRunsModal = useCallback(() => {
    setRunsJob(null);
    setRunOutputs([]);
    setSelectedRun(null);
    setRunDetail("");
  }, []);
  const runsModalRef = useModalBehavior({
    open: runsJob !== null,
    onClose: closeRunsModal,
  });

  // Skills installed in the profile a job will run under, for the
  // attach-skill selector (parity with `hermes cron edit --add-skill`).
  // Keyed on the create-modal profile; the edit modal reuses the list —
  // a job's current skills are always shown even if not in it.
  const [availableSkills, setAvailableSkills] = useState<SkillInfo[]>([]);

  const openEditModal = useCallback((job: CronJob) => {
    setEditJob(job);
    setEditPrompt(getJobPrompt(job));
    setEditScheduleState(
      parseScheduleToState(job.schedule, asText(job.schedule_display) || undefined),
    );
    setEditName(getJobName(job));
    setEditDeliver(asText(job.deliver) || "local");
    setEditSkills(Array.isArray(job.skills) ? job.skills.filter(Boolean) : []);
    setEditExecutionMode(inferExecutionMode(job));
    setEditScript(asText(job.script));
    setEditHttpForm(httpFormFromJob(job));
  }, []);

  const openRunHistory = useCallback(async (job: CronJob) => {
    const profile = getJobProfile(job);
    setRunsJob(job);
    setRunOutputs([]);
    setSelectedRun(null);
    setRunDetail("");
    setRunsLoading(true);
    try {
      const res = await api.getCronJobOutputs(job.id, profile);
      setRunOutputs(res.outputs);
    } catch (e) {
      showToast(`${t.cron.runHistoryLoadFailed ?? "Failed to load run history"}: ${e}`, "error");
    } finally {
      setRunsLoading(false);
    }
  }, [showToast, t.cron.runHistoryLoadFailed]);

  const selectRunOutput = useCallback(async (run: CronJobOutput, job: CronJob) => {
    setSelectedRun(run);
    if (run.content) {
      setRunDetail(run.content);
      return;
    }
    setRunDetailLoading(true);
    try {
      const detail = await api.getCronJobOutput(job.id, run.output_id, getJobProfile(job));
      setRunDetail(detail.content ?? detail.preview ?? "");
    } catch (e) {
      setRunDetail(run.preview ?? "");
      showToast(`${t.cron.runHistoryLoadFailed ?? "Failed to load run history"}: ${e}`, "error");
    } finally {
      setRunDetailLoading(false);
    }
  }, [showToast, t.cron.runHistoryLoadFailed]);

  const loadJobs = useCallback(() => {
    api
      .getCronJobs(selectedProfile)
      .then(setJobs)
      .catch(() => showToast(t.common.loading, "error"))
      .finally(() => setLoading(false));
  }, [selectedProfile, showToast, t.common.loading]);

  useEffect(() => {
    api
      .getProfiles()
      .then((res) => setProfiles(res.profiles))
      .catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    api
      .getCronDeliveryTargets()
      .then((res) => setDeliveryTargets(res.targets))
      .catch(() =>
        // Fall back to local-only so the modal still works if the endpoint fails.
        setDeliveryTargets([
          { id: "local", name: "Local", home_target_set: true, home_env_var: null },
        ]),
      );
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Load installed skills for the profile new jobs will be created under.
  // "" / "default" maps to the dashboard's own profile via the optional
  // ?profile= scoping on /api/skills.
  useEffect(() => {
    let cancelled = false;
    api
      .getSkills(createProfile === "default" ? undefined : createProfile)
      .then((s) => {
        if (!cancelled)
          setAvailableSkills(
            [...s].sort((a, b) => a.name.localeCompare(b.name)),
          );
      })
      .catch(() => !cancelled && setAvailableSkills([]));
    return () => {
      cancelled = true;
    };
  }, [createProfile]);

  const scheduleString = buildScheduleString(scheduleState);

  // Label for a delivery option. Configured platforms missing their cron home
  // channel are still offered (option B), annotated so the user knows what to
  // fix rather than wondering why delivery silently no-ops.
  const deliverLabel = useCallback(
    (target: CronDeliveryTarget): string => {
      const deliveryLabels = t.cron.delivery as Record<string, string | undefined>;
      const base =
        target.id === "local"
          ? t.cron.delivery.local
          : deliveryLabels[target.id] ?? target.name;
      if (target.id !== "local" && !target.home_target_set) {
        const hint = t.cron.delivery.needsHomeChannel ?? "set a home channel first";
        return `${base} — ${hint}`;
      }
      return base;
    },
    [t.cron.delivery],
  );

  const renderDeliverOptions = useCallback(
    () =>
      deliveryTargets.map((target) => (
        <SelectOption key={target.id} value={target.id}>
          {deliverLabel(target)}
        </SelectOption>
      )),
    [deliveryTargets, deliverLabel],
  );

  // The edit modal must always show the job's current target, even if that
  // platform is no longer configured (e.g. job created via CLI, or the
  // gateway was later removed) — otherwise the value would silently vanish
  // from the dropdown and saving would drop it.
  const renderEditDeliverOptions = useCallback(
    (current: string) => {
      const known = new Set(deliveryTargets.map((target) => target.id));
      const options = deliveryTargets.map((target) => (
        <SelectOption key={target.id} value={target.id}>
          {deliverLabel(target)}
        </SelectOption>
      ));
      if (current && !known.has(current)) {
        options.push(
          <SelectOption key={current} value={current}>
            {current}
          </SelectOption>,
        );
      }
      return options;
    },
    [deliveryTargets, deliverLabel],
  );

  const onlyLocalAvailable =
    deliveryTargets.filter((target) => target.id !== "local").length === 0;

  const handleCreate = async () => {
    if (!scheduleString) {
      showToast(`${t.cron.schedule} required`, "error");
      return;
    }
    const validationError = validateCronExecution(
      executionMode,
      prompt,
      script,
      jobSkills,
      httpForm,
      {
        scriptRequired: t.cron.scriptRequired ?? "Script path is required",
        promptOrSkillsRequired:
          t.cron.promptOrSkillsRequired ?? "Agent mode requires a prompt or at least one skill",
        httpUrlRequired: t.cron.httpUrlRequired ?? "HTTP URL is required",
      },
    );
    if (validationError) {
      showToast(validationError, "error");
      return;
    }
    setCreating(true);
    try {
      await api.createCronJob(
        {
          schedule: scheduleString,
          name: name.trim() || undefined,
          deliver,
          ...buildCronExecutionPayload(executionMode, prompt, script, jobSkills, httpForm),
        },
        createProfile,
      );
      showToast(t.common.create + " ✓", "success");
      setPrompt("");
      setScheduleState(DEFAULT_SCHEDULE_STATE);
      setName("");
      setDeliver("local");
      setJobSkills([]);
      setExecutionMode("agent");
      setScript("");
      setHttpForm({ ...EMPTY_HTTP_FORM });
      setCreateModalOpen(false);
      loadJobs();
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${e}`, "error");
    } finally {
      setCreating(false);
    }
  };

  const handleEdit = async () => {
    if (!editJob) return;
    const editScheduleString = buildScheduleString(editScheduleState);
    if (!editScheduleString) {
      showToast(`${t.cron.schedule} required`, "error");
      return;
    }
    const validationError = validateCronExecution(
      editExecutionMode,
      editPrompt,
      editScript,
      editSkills,
      editHttpForm,
      {
        scriptRequired: t.cron.scriptRequired ?? "Script path is required",
        promptOrSkillsRequired:
          t.cron.promptOrSkillsRequired ?? "Agent mode requires a prompt or at least one skill",
        httpUrlRequired: t.cron.httpUrlRequired ?? "HTTP URL is required",
      },
    );
    if (validationError) {
      showToast(validationError, "error");
      return;
    }
    setSaving(true);
    try {
      await api.updateCronJob(
        editJob.id,
        {
          schedule: editScheduleString,
          name: editName.trim(),
          deliver: editDeliver,
          ...buildCronExecutionPayload(editExecutionMode, editPrompt, editScript, editSkills, editHttpForm),
        },
        getJobProfile(editJob),
      );
      showToast(t.cron.savedChanges ?? "Saved changes ✓", "success");
      setEditJob(null);
      loadJobs();
    } catch (e) {
      showToast(`${t.config.failedToSave}: ${e}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handlePauseResume = async (job: CronJob) => {
    try {
      const isPaused = getJobState(job) === "paused";
      const profile = getJobProfile(job);
      if (isPaused) {
        await api.resumeCronJob(job.id, profile);
        showToast(
          `${t.cron.resume}: "${truncateText(getJobTitle(job), 30)}"`,
          "success",
        );
      } else {
        await api.pauseCronJob(job.id, profile);
        showToast(
          `${t.cron.pause}: "${truncateText(getJobTitle(job), 30)}"`,
          "success",
        );
      }
      loadJobs();
    } catch (e) {
      showToast(`${t.status.error}: ${e}`, "error");
    }
  };

  const handleTrigger = async (job: CronJob) => {
    try {
      const updated = await api.triggerCronJob(job.id, getJobProfile(job));
      if (updated.last_delivery_error) {
        showToast(
          `${t.cron.deliveryFailed ?? "Delivery failed"}: ${updated.last_delivery_error}`,
          "error",
        );
      } else {
        showToast(
          `${t.cron.triggerNow}: "${truncateText(getJobTitle(job), 30)}"`,
          "success",
        );
      }
      loadJobs();
    } catch (e) {
      showToast(`${t.status.error}: ${e}`, "error");
    }
  };

  const jobDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const { profile, id } = splitJobKey(key);
        const job = jobs.find((j) => getJobKey(j) === key);
        try {
          await api.deleteCronJob(id, profile);
          showToast(
            `${t.common.delete}: "${job ? truncateText(getJobTitle(job), 30) : id}"`,
            "success",
          );
          loadJobs();
        } catch (e) {
          showToast(`${t.status.error}: ${e}`, "error");
          throw e;
        }
      },
      [jobs, loadJobs, showToast, t.common.delete, t.status.error],
    ),
  });

  // Create lives in-page (next to Jobs/Blueprints tabs) — the header slot
  // races with loading/profile remounts and can flash then disappear.

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  const pendingJob = jobDelete.pendingId
    ? jobs.find((j) => getJobKey(j) === jobDelete.pendingId)
    : null;

  return (
    <div className="flex flex-col gap-6">
      <PluginSlot name="cron:top" />
      <Toast toast={toast} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Segmented
          value={view}
          onChange={(v) => setView(v as "jobs" | "blueprints")}
          options={[
            { value: "jobs", label: t.cron.jobs ?? "Jobs" },
            { value: "blueprints", label: t.cron.blueprints ?? "Blueprints" },
          ]}
        />
        {view === "jobs" && (
          <Button
            className="uppercase shrink-0 self-start sm:self-auto"
            size="sm"
            onClick={() => setCreateModalOpen(true)}
          >
            {t.common.create}
          </Button>
        )}
      </div>

      {view === "blueprints" && (
        <AutomationBlueprints
          profile={selectedProfile === "all" ? "default" : selectedProfile}
          onCreated={loadJobs}
        />
      )}


      <DeleteConfirmDialog
        open={jobDelete.isOpen}
        onCancel={jobDelete.cancel}
        onConfirm={jobDelete.confirm}
        title={t.cron.confirmDeleteTitle}
        description={
          pendingJob
            ? `"${truncateText(getJobTitle(pendingJob), 40)}" — ${
                t.cron.confirmDeleteMessage
              }`
            : t.cron.confirmDeleteMessage
        }
        loading={jobDelete.isDeleting}
      />

      {/* Create job modal */}
      {createModalOpen && (
        <div
          ref={createModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setCreateModalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setCreateModalOpen(false)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label={t.cron.closeAriaLabel ?? "Close"}
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border">
              <h2
                id="create-cron-title"
                className="font-mondwest text-display text-base tracking-wider"
              >
                {t.cron.newJob}
              </h2>
            </header>

            <div className="p-5 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="cron-profile">{t.cron.profile ?? "Profile"}</Label>
                <Select
                  id="cron-profile"
                  value={createProfile}
                  onValueChange={(v) => setSelectedProfile(v)}
                >
                  {profiles.map((profile) => (
                    <SelectOption key={profile.name} value={profile.name}>
                      {profileLabel(profile.name)}
                    </SelectOption>
                  ))}
                </Select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="cron-name">{t.cron.nameOptional}</Label>
                <Input
                  id="cron-name"
                  autoFocus
                  placeholder={t.cron.namePlaceholder}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="cron-execution-mode">{t.cron.executionMode ?? "Execution mode"}</Label>
                <Select
                  id="cron-execution-mode"
                  value={executionMode}
                  onValueChange={(v) => {
                    const mode = v as CronExecutionMode;
                    setExecutionMode(mode);
                    if (mode === "no_agent") setJobSkills([]);
                  }}
                >
                  <SelectOption value="agent">
                    {t.cron.executionModes?.agent ?? "Agent (prompt / skills)"}
                  </SelectOption>
                  <SelectOption value="script_agent">
                    {t.cron.executionModes?.scriptAgent ?? "Script + Agent"}
                  </SelectOption>
                  <SelectOption value="no_agent">
                    {t.cron.executionModes?.noAgent ?? "Script only (no Agent)"}
                  </SelectOption>
                  <SelectOption value="http">
                    {t.cron.executionModes?.http ?? "HTTP request"}
                  </SelectOption>
                </Select>
              </div>

              {executionMode === "http" && (
                <CronHttpFields idPrefix="cron" form={httpForm} onChange={setHttpForm} t={t} />
              )}

              {modeUsesScript(executionMode) && (
                <div className="grid gap-2">
                  <Label htmlFor="cron-script">{t.cron.script ?? "Script"}</Label>
                  <Input
                    id="cron-script"
                    placeholder={t.cron.scriptPlaceholder ?? "check_disk.py"}
                    value={script}
                    onChange={(e) => setScript(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {(t.cron.scriptHint ?? "Relative path under scripts/ in the profile data dir.").replace(
                      "{profile}",
                      createProfile,
                    )}
                  </p>
                </div>
              )}

              {executionMode !== "http" && (
                <div className="grid gap-2">
                  <Label htmlFor="cron-prompt">
                    {executionMode === "no_agent"
                      ? `${t.cron.prompt} (${t.cron.nameOptional})`
                      : t.cron.prompt}
                  </Label>
                  <textarea
                    id="cron-prompt"
                    className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
                    placeholder={t.cron.promptPlaceholder}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                  />
                </div>
              )}

              <ScheduleBuilder
                value={scheduleState}
                onChange={setScheduleState}
              />

              <div className="grid gap-2">
                <Label htmlFor="cron-deliver">{t.cron.deliverTo}</Label>
                <Select
                  id="cron-deliver"
                  value={deliver}
                  onValueChange={(v) => setDeliver(v)}
                >
                  {renderDeliverOptions()}
                </Select>
                {onlyLocalAvailable && (
                  <p className="text-xs text-muted-foreground">
                    {t.cron.delivery.noneConfigured ??
                      "No messaging platforms configured. Set one up under Channels to deliver reports."}
                  </p>
                )}
              </div>

              {(executionMode === "agent" || executionMode === "script_agent") && (
                <div className="grid gap-2">
                  <Label htmlFor="cron-skills">{t.cron.skillsOptional ?? "Skills (optional)"}</Label>
                  <SkillsPicker
                    id="cron-skills"
                    available={availableSkills}
                    selected={jobSkills}
                    onChange={setJobSkills}
                    emptyLabel={t.cron.noSkillsInstalled ?? "No skills installed for this profile."}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t.cron.skillsHint ??
                      "Selected skills load before the prompt runs — the schedule decides when, skills decide how."}
                  </p>
                </div>
              )}

              {executionMode === "no_agent" && (
                <p className="text-xs text-muted-foreground">
                  {t.cron.noAgentSkillsHint ??
                    "No-agent mode runs the script only and delivers stdout — skills are ignored."}
                </p>
              )}

              <div className="flex justify-end">
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={handleCreate}
                  disabled={creating}
                  prefix={creating ? <Spinner /> : undefined}
                >
                  {creating ? t.common.creating : t.common.create}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit job modal */}
      {editJob && (
        <div
          ref={editModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setEditJob(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-cron-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setEditJob(null)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label={t.cron.closeAriaLabel ?? "Close"}
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border">
              <h2
                id="edit-cron-title"
                className="font-mondwest text-display text-base tracking-wider"
              >
                {t.cron.editJob ?? "Edit job"}
              </h2>
            </header>

            <div className="p-5 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="edit-cron-name">{t.cron.nameOptional}</Label>
                <Input
                  id="edit-cron-name"
                  autoFocus
                  placeholder={t.cron.namePlaceholder}
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="edit-cron-execution-mode">{t.cron.executionMode ?? "Execution mode"}</Label>
                <Select
                  id="edit-cron-execution-mode"
                  value={editExecutionMode}
                  onValueChange={(v) => {
                    const mode = v as CronExecutionMode;
                    setEditExecutionMode(mode);
                    if (mode === "no_agent") setEditSkills([]);
                  }}
                >
                  <SelectOption value="agent">
                    {t.cron.executionModes?.agent ?? "Agent (prompt / skills)"}
                  </SelectOption>
                  <SelectOption value="script_agent">
                    {t.cron.executionModes?.scriptAgent ?? "Script + Agent"}
                  </SelectOption>
                  <SelectOption value="no_agent">
                    {t.cron.executionModes?.noAgent ?? "Script only (no Agent)"}
                  </SelectOption>
                  <SelectOption value="http">
                    {t.cron.executionModes?.http ?? "HTTP request"}
                  </SelectOption>
                </Select>
              </div>

              {editExecutionMode === "http" && (
                <CronHttpFields idPrefix="edit-cron" form={editHttpForm} onChange={setEditHttpForm} t={t} />
              )}

              {modeUsesScript(editExecutionMode) && (
                <div className="grid gap-2">
                  <Label htmlFor="edit-cron-script">{t.cron.script ?? "Script"}</Label>
                  <Input
                    id="edit-cron-script"
                    placeholder={t.cron.scriptPlaceholder ?? "check_disk.py"}
                    value={editScript}
                    onChange={(e) => setEditScript(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {(t.cron.scriptHint ?? "Relative path under scripts/ in the profile data dir.").replace(
                      "{profile}",
                      getJobProfile(editJob),
                    )}
                  </p>
                </div>
              )}

              {editExecutionMode !== "http" && (
                <div className="grid gap-2">
                  <Label htmlFor="edit-cron-prompt">
                    {editExecutionMode === "no_agent"
                      ? `${t.cron.prompt} (${t.cron.nameOptional})`
                      : t.cron.prompt}
                  </Label>
                  <textarea
                    id="edit-cron-prompt"
                    className="flex min-h-[80px] w-full border border-border bg-background/40 px-3 py-2 text-sm font-courier shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30 focus-visible:border-foreground/25"
                    placeholder={t.cron.promptPlaceholder}
                    value={editPrompt}
                    onChange={(e) => setEditPrompt(e.target.value)}
                  />
                </div>
              )}

              <ScheduleBuilder value={editScheduleState} onChange={setEditScheduleState} />

              <div className="grid gap-2">
                <Label htmlFor="edit-cron-deliver">{t.cron.deliverTo}</Label>
                <Select
                  id="edit-cron-deliver"
                  value={editDeliver}
                  onValueChange={(v) => setEditDeliver(v)}
                >
                  {renderEditDeliverOptions(editDeliver)}
                </Select>
              </div>

              {(editExecutionMode === "agent" || editExecutionMode === "script_agent") && (
                <div className="grid gap-2">
                  <Label htmlFor="edit-cron-skills">{t.cron.skills ?? "Skills"}</Label>
                  <SkillsPicker
                    id="edit-cron-skills"
                    available={availableSkills}
                    selected={editSkills}
                    onChange={setEditSkills}
                    emptyLabel={t.cron.noSkillsInstalled ?? "No skills installed for this profile."}
                  />
                </div>
              )}

              {editExecutionMode === "no_agent" && (
                <p className="text-xs text-muted-foreground">
                  {t.cron.noAgentSkillsHint ??
                    "No-agent mode runs the script only and delivers stdout — skills are ignored."}
                </p>
              )}

              <div className="flex justify-end">
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={handleEdit}
                  disabled={saving}
                  prefix={saving ? <Spinner /> : undefined}
                >
                  {saving ? t.common.loading : (t.cron.saveChanges ?? "Save changes")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {runsJob && (
        <div
          ref={runsModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && closeRunsModal()}
          role="dialog"
          aria-modal="true"
          aria-labelledby="cron-runs-title"
        >
          <div className={cn(themedBody, "relative w-full max-w-3xl border border-border bg-card shadow-2xl flex flex-col max-h-[85vh]")}>
            <Button
              ghost
              size="icon"
              onClick={closeRunsModal}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label={t.cron.closeAriaLabel ?? "Close"}
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border shrink-0">
              <h2
                id="cron-runs-title"
                className="font-mondwest text-display text-base tracking-wider"
              >
                {t.cron.runHistoryTitle ?? "Run history"} — {getJobTitle(runsJob)}
              </h2>
              <p className="text-xs text-muted-foreground mt-1 font-mono-ui">
                {runsJob.id}
              </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-[minmax(0,240px)_1fr] min-h-0 flex-1">
              <div className="border-b md:border-b-0 md:border-r border-border overflow-y-auto max-h-[40vh] md:max-h-none">
                {runsLoading ? (
                  <div className="p-5 flex items-center gap-2 text-sm text-muted-foreground">
                    <Spinner />
                    {t.common.loading}
                  </div>
                ) : runOutputs.length === 0 ? (
                  <p className="p-5 text-sm text-muted-foreground">
                    {t.cron.runHistoryEmpty ?? "No runs recorded yet."}
                  </p>
                ) : (
                  <ul className="divide-y divide-border">
                    {runOutputs.map((run) => {
                      const active = selectedRun?.output_id === run.output_id;
                      const failed = run.status === "failed";
                      return (
                        <li key={run.output_id}>
                          <button
                            type="button"
                            className={cn(
                              "w-full text-left px-4 py-3 hover:bg-muted/40 transition-colors",
                              active && "bg-muted/60",
                            )}
                            onClick={() => selectRunOutput(run, runsJob)}
                          >
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <span className="text-xs font-mono-ui text-muted-foreground">
                                {formatTime(run.run_at)}
                              </span>
                              <Badge tone={failed ? "destructive" : "success"}>
                                {failed
                                  ? (t.cron.runStatusFailed ?? "Failed")
                                  : (t.cron.runStatusOk ?? "OK")}
                              </Badge>
                            </div>
                            <p className="text-xs text-foreground/80 line-clamp-2">
                              {run.preview || "—"}
                            </p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="overflow-y-auto p-5 min-h-[200px]">
                {!selectedRun ? (
                  <p className="text-sm text-muted-foreground">
                    {t.cron.runHistorySelect ?? "Select a run on the left to view details."}
                  </p>
                ) : runDetailLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Spinner />
                    {t.common.loading}
                  </div>
                ) : (
                  <pre className="text-xs font-courier whitespace-pre-wrap break-words text-foreground/90">
                    {runDetail || selectedRun.preview || "—"}
                  </pre>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {view === "jobs" && (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <H2
            variant="sm"
            className="flex items-center gap-2 text-muted-foreground"
          >
            <Clock className="h-4 w-4" />
            {t.cron.scheduledJobs} ({jobs.length})
          </H2>

          <div className="grid gap-1 min-w-[220px]">
            <Label htmlFor="cron-profile-filter">{t.cron.profile ?? "Profile"}</Label>
            <Select
              id="cron-profile-filter"
              value={selectedProfile}
              onValueChange={(v) => setSelectedProfile(v)}
            >
              <SelectOption value="all">{t.cron.allProfiles ?? "All profiles"}</SelectOption>
              {profiles.map((profile) => (
                <SelectOption key={profile.name} value={profile.name}>
                  {profileLabel(profile.name)}
                </SelectOption>
              ))}
            </Select>
          </div>
        </div>

        {jobs.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {t.cron.noJobs}
            </CardContent>
          </Card>
        )}

        {jobs.map((job) => {
          const state = getJobState(job);
          const promptText = getJobPrompt(job);
          const title = getJobTitle(job);
          const hasName = Boolean(getJobName(job));
          const deliver = asText(job.deliver);
          const profile = getJobProfile(job);
          const jobKey = getJobKey(job);

          return (
            <Card key={jobKey}>
              <CardContent className="flex items-start gap-4 py-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm truncate">
                      {title}
                    </span>
                    <Badge tone={STATUS_TONE[state] ?? "secondary"}>
                      {state}
                    </Badge>
                    <Badge tone="outline">{profileLabel(profile)}</Badge>
                    {deliver && deliver !== "local" && (
                      <Badge tone="outline">{deliver}</Badge>
                    )}
                    {Array.isArray(job.skills) && job.skills.length > 0 && (
                      <Badge tone="outline" title={job.skills.join(", ")}>
                        {job.skills.length === 1
                          ? job.skills[0]
                          : `${job.skills.length} skills`}
                      </Badge>
                    )}
                    {job.http && (
                      <Badge tone="outline">{t.cron.modeHttp ?? "http"}</Badge>
                    )}
                    {!job.http && job.no_agent && (
                      <Badge tone="outline">{t.cron.modeNoAgent ?? "no agent"}</Badge>
                    )}
                    {!job.http && !job.no_agent && job.script && (
                      <Badge tone="outline">{t.cron.modeScript ?? "script"}</Badge>
                    )}
                  </div>
                  {hasName && promptText && (
                    <p className="text-xs text-muted-foreground truncate mb-1">
                      {truncateText(promptText, 100)}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="font-mono-ui">
                      {getJobScheduleDisplay(job, scheduleDescribeStrings)}
                    </span>
                    <span>
                      {t.cron.last}: {formatTime(job.last_run_at)}
                    </span>
                    <span>
                      {t.cron.next}: {formatTime(job.next_run_at)}
                    </span>
                  </div>
                  {job.last_error && (
                    <p className="text-xs text-destructive mt-1">
                      {job.last_error}
                    </p>
                  )}
                  {job.last_delivery_error && (
                    <p className="text-xs text-destructive mt-1">
                      {t.cron.deliveryFailed ?? "Delivery failed"}: {job.last_delivery_error}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    ghost
                    size="icon"
                    title={state === "paused" ? t.cron.resume : t.cron.pause}
                    aria-label={
                      state === "paused" ? t.cron.resume : t.cron.pause
                    }
                    onClick={() => handlePauseResume(job)}
                    className={
                      state === "paused" ? "text-success" : "text-warning"
                    }
                  >
                    {state === "paused" ? <Play /> : <Pause />}
                  </Button>

                  <Button
                    ghost
                    size="icon"
                    title={t.cron.triggerNow}
                    aria-label={t.cron.triggerNow}
                    onClick={() => handleTrigger(job)}
                  >
                    <Zap />
                  </Button>

                  <Button
                    ghost
                    size="icon"
                    title={t.cron.runHistory ?? "Run history"}
                    aria-label={t.cron.runHistory ?? "Run history"}
                    onClick={() => openRunHistory(job)}
                  >
                    <History />
                  </Button>

                  <Button
                    ghost
                    size="icon"
                    title={t.cron.editJob ?? "Edit job"}
                    aria-label={t.cron.editJob ?? "Edit job"}
                    onClick={() => openEditModal(job)}
                  >
                    <Pencil />
                  </Button>

                  <Button
                    ghost
                    destructive
                    size="icon"
                    title={t.common.delete}
                    aria-label={t.common.delete}
                    onClick={() => jobDelete.requestDelete(jobKey)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      )}

      <PluginSlot name="cron:bottom" />
    </div>
  );
}
