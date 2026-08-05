import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Brain,
  Cpu,
  Database,
  HardDrive,
  KeyRound,
  Play,
  Plus,
  Power,
  RotateCw,
  Server,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Select, SelectOption } from "@nous-research/ui/ui/components/select";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { ConfirmDialog } from "@nous-research/ui/ui/components/confirm-dialog";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { cn, themedBody } from "@/lib/utils";
import { api } from "@/lib/api";
import { gatewayStatusText } from "@/components/SidebarStatusStrip";
import { useI18n } from "@/i18n";
import type {
  StatusResponse,
  MemoryStatus,
  CredentialPoolProvider,
  CheckpointsResponse,
  HooksResponse,
  HookEntry,
  SystemStats,
  CuratorStatus,
} from "@/lib/api";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDuration(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/**
 * Live action-log viewer for the spawn-based admin actions (doctor, audit,
 * backup, import, skills update, checkpoints prune, gateway start/stop).
 * Polls /api/actions/<name>/status until the process exits.
 */
function ActionLogViewer({
  action,
  onClose,
}: {
  action: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [lines, setLines] = useState<string[]>([]);
  const [running, setRunning] = useState(true);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const st = await api.getActionStatus(action, 400);
        if (cancelled) return;
        setLines(st.lines);
        setRunning(st.running);
        setExitCode(st.exit_code);
        if (st.running) timer.current = setTimeout(poll, 1200);
      } catch {
        if (!cancelled) setRunning(false);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [action]);

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-muted-foreground" />
            <span className="font-mono text-sm">{action}</span>
            {running ? (
              <Badge tone="warning">{t.system?.logRunning ?? "running"}</Badge>
            ) : (
              <Badge tone={exitCode === 0 ? "success" : "destructive"}>
                {exitCode === 0
                  ? (t.system?.logDone ?? "done")
                  : (t.system?.logExitCode?.replace("{exitCode}", String(exitCode)) ?? `exit ${exitCode}`)}
              </Badge>
            )}
          </div>
          <Button ghost size="icon" onClick={onClose} aria-label={t.system?.logCloseAriaLabel ?? "Close log"}>
            <X />
          </Button>
        </div>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words bg-background/50 border border-border p-3 text-xs font-mono text-muted-foreground">
          {lines.length ? lines.join("\n") : (t.system?.logStarting ?? "Starting…")}
        </pre>
      </CardContent>
    </Card>
  );
}

const HOOK_EVENTS_FALLBACK = [
  "pre_tool_call",
  "post_tool_call",
  "pre_llm_call",
  "post_llm_call",
  "on_session_start",
  "on_session_end",
];

export default function SystemPage() {
  const { t } = useI18n();
  const { toast, showToast } = useToast();

  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [memory, setMemory] = useState<MemoryStatus | null>(null);
  const [pool, setPool] = useState<CredentialPoolProvider[]>([]);
  const [checkpoints, setCheckpoints] = useState<CheckpointsResponse | null>(
    null,
  );
  const [hooks, setHooks] = useState<HooksResponse | null>(null);
  const [curator, setCurator] = useState<CuratorStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [activeAction, setActiveAction] = useState<string | null>(null);

  // Add-credential form.
  const [credProvider, setCredProvider] = useState("openrouter");
  const [credKey, setCredKey] = useState("");
  const [credLabel, setCredLabel] = useState("");
  const [addingCred, setAddingCred] = useState(false);

  const [importPath, setImportPath] = useState("");
  // Restore-from-backup is destructive (overwrites the live config) and the
  // spawned `hermes import` runs non-interactively (stdin is /dev/null), so
  // its CLI "Continue? [y/N]" prompt would auto-abort. The dashboard owns the
  // consent: confirm here, then call the endpoint with force=true.
  const [importConfirmOpen, setImportConfirmOpen] = useState(false);

  // Create-hook modal.
  const [hookModalOpen, setHookModalOpen] = useState(false);
  const closeHookModal = useCallback(() => setHookModalOpen(false), []);
  const hookModalRef = useModalBehavior({
    open: hookModalOpen,
    onClose: closeHookModal,
  });
  const [hookEvent, setHookEvent] = useState("pre_tool_call");
  const [hookCommand, setHookCommand] = useState("");
  const [hookMatcher, setHookMatcher] = useState("");
  const [hookTimeout, setHookTimeout] = useState("");
  const [hookApprove, setHookApprove] = useState(true);
  const [creatingHook, setCreatingHook] = useState(false);

  const loadAll = useCallback(() => {
    Promise.allSettled([
      api.getStatus(),
      api.getSystemStats(),
      api.getMemory(),
      api.getCredentialPool(),
      api.getCheckpoints(),
      api.getHooks(),
      api.getCurator(),
    ])
      .then(([s, st, m, p, c, h, cur]) => {
        if (s.status === "fulfilled") setStatus(s.value);
        if (st.status === "fulfilled") setStats(st.value);
        if (m.status === "fulfilled") setMemory(m.value);
        if (p.status === "fulfilled") setPool(p.value.providers);
        if (c.status === "fulfilled") setCheckpoints(c.value);
        if (h.status === "fulfilled") setHooks(h.value);
        if (cur.status === "fulfilled") setCurator(cur.value);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Gateway lifecycle ──────────────────────────────────────────────
  const runGateway = async (verb: "start" | "stop" | "restart") => {
    try {
      if (verb === "start") {
        await api.startGateway();
        setActiveAction("gateway-start");
      } else if (verb === "stop") {
        await api.stopGateway();
        setActiveAction("gateway-stop");
      } else {
        await api.restartGateway();
        setActiveAction("gateway-restart");
      }
      showToast(
        t.system?.gatewayStartedToast?.replace("{verb}", verb) ?? `Gateway ${verb} started`,
        "success",
      );
      setTimeout(loadAll, 3000);
    } catch (e) {
      showToast(
        t.system?.gatewayFailedToast?.replace("{verb}", verb).replace("{error}", String(e)) ?? `Gateway ${verb} failed: ${e}`,
        "error",
      );
    }
  };

  // ── Curator ────────────────────────────────────────────────────────
  const toggleCuratorPaused = async () => {
    if (!curator) return;
    try {
      await api.setCuratorPaused(!curator.paused);
      showToast(
        curator.paused
          ? (t.system?.curatorResumedToast ?? "Curator resumed")
          : (t.system?.curatorPausedToast ?? "Curator paused"),
        "success",
      );
      loadAll();
    } catch (e) {
      showToast(
        t.system?.curatorToggleFailedToast?.replace("{error}", String(e)) ?? `Curator toggle failed: ${e}`,
        "error",
      );
    }
  };

  // ── Memory ─────────────────────────────────────────────────────────
  // Memory provider selection lives on the /plugins page now (see the
  // read-only display + link below); the dropdown was intentionally
  // dropped from this card during the admin-panel refresh.
  const memoryReset = useConfirmDelete({
    onDelete: useCallback(
      async (target: string) => {
        try {
          const res = await api.resetMemory(
            target as "all" | "memory" | "user",
          );
          showToast(
            t.system?.memoryResetToast?.replace("{deleted}", res.deleted.join(", ") || "nothing") ?? `Reset: ${res.deleted.join(", ") || "nothing"}`,
            "success",
          );
          loadAll();
        } catch (e) {
          showToast(
            t.system?.memoryResetFailedToast?.replace("{error}", String(e)) ?? `Reset failed: ${e}`,
            "error",
          );
          throw e;
        }
      },
      [loadAll, showToast, t],
    ),
  });

  // ── Credential pool ────────────────────────────────────────────────
  const addCredential = async () => {
    if (!credProvider.trim() || !credKey.trim()) {
      showToast(t.system?.credRequiredError ?? "Provider and API key required", "error");
      return;
    }
    setAddingCred(true);
    try {
      await api.addCredentialPoolEntry(
        credProvider.trim(),
        credKey.trim(),
        credLabel.trim() || undefined,
      );
      showToast(t.system?.credAddedSuccess ?? "Credential added", "success");
      setCredKey("");
      setCredLabel("");
      loadAll();
    } catch (e) {
      showToast(
        t.system?.credAddFailedError?.replace("{error}", String(e)) ?? `Failed to add credential: ${e}`,
        "error",
      );
    } finally {
      setAddingCred(false);
    }
  };

  const credDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const [provider, idxStr] = key.split("|");
        try {
          await api.removeCredentialPoolEntry(provider, Number(idxStr));
          showToast(t.system?.credRemovedSuccess ?? "Credential removed", "success");
          loadAll();
        } catch (e) {
          showToast(
            t.system?.credRemoveFailedError?.replace("{error}", String(e)) ?? `Failed to remove: ${e}`,
            "error",
          );
          throw e;
        }
      },
      [loadAll, showToast, t],
    ),
  });

  // ── Operations ─────────────────────────────────────────────────────
  const runOp = async (fn: () => Promise<{ name: string }>, label: string) => {
    try {
      const res = await fn();
      setActiveAction(res.name);
      showToast(`${label} started`, "success");
    } catch (e) {
      showToast(`${label} failed: ${e}`, "error");
    }
  };

  const checkpointsPrune = useConfirmDelete({
    onDelete: useCallback(async () => {
      try {
        const res = await api.pruneCheckpoints();
        setActiveAction(res.name);
        showToast(t.system?.checkpointPruneStarted ?? "Checkpoint prune started", "success");
      } catch (e) {
        showToast(
          t.system?.checkpointPruneFailed?.replace("{error}", String(e)) ?? `Prune failed: ${e}`,
          "error",
        );
        throw e;
      }
    }, [showToast, t]),
  });

  // ── Hooks ──────────────────────────────────────────────────────────
  const createHook = async () => {
    if (!hookCommand.trim()) {
      showToast(t.system?.hookCommandRequired ?? "Command is required", "error");
      return;
    }
    setCreatingHook(true);
    try {
      await api.createHook({
        event: hookEvent,
        command: hookCommand.trim(),
        matcher: hookMatcher.trim() || undefined,
        timeout: hookTimeout.trim() ? Number(hookTimeout) : undefined,
        approve: hookApprove,
      });
      showToast(t.system?.hookCreated ?? "Hook created", "success");
      setHookCommand("");
      setHookMatcher("");
      setHookTimeout("");
      setHookModalOpen(false);
      loadAll();
    } catch (e) {
      showToast(
        t.system?.hookCreateFailed?.replace("{error}", String(e)) ?? `Failed to create hook: ${e}`,
        "error",
      );
    } finally {
      setCreatingHook(false);
    }
  };

  const hookDelete = useConfirmDelete({
    onDelete: useCallback(
      async (key: string) => {
        const sep = key.indexOf("|");
        const event = key.slice(0, sep);
        const command = key.slice(sep + 1);
        try {
          await api.deleteHook(event, command);
          showToast(t.system?.hookRemoved ?? "Hook removed", "success");
          loadAll();
        } catch (e) {
          showToast(
            t.system?.hookRemoveFailed?.replace("{error}", String(e)) ?? `Failed to remove hook: ${e}`,
            "error",
          );
          throw e;
        }
      },
      [loadAll, showToast, t],
    ),
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  const gatewayRunning = status?.gateway_running;
  const gatewayStatusLabel = status
    ? gatewayStatusText(status, t).label
    : "—";
  const validEvents = hooks?.valid_events?.length
    ? hooks.valid_events
    : HOOK_EVENTS_FALLBACK;

  return (
    <div className="flex flex-col gap-8">
      <Toast toast={toast} />

      <DeleteConfirmDialog
        open={memoryReset.isOpen}
        onCancel={memoryReset.cancel}
        onConfirm={memoryReset.confirm}
        title={t.system?.memoryResetTitle ?? "Reset memory"}
        description={t.system?.memoryResetDescription ?? "This permanently erases the selected built-in memory files. This cannot be undone."}
        loading={memoryReset.isDeleting}
      />
      <DeleteConfirmDialog
        open={credDelete.isOpen}
        onCancel={credDelete.cancel}
        onConfirm={credDelete.confirm}
        title={t.system?.credRemoveTitle ?? "Remove credential"}
        description={t.system?.credRemoveDescription ?? "Remove this pooled API key? The agent will no longer rotate through it."}
        loading={credDelete.isDeleting}
      />
      <DeleteConfirmDialog
        open={checkpointsPrune.isOpen}
        onCancel={checkpointsPrune.cancel}
        onConfirm={checkpointsPrune.confirm}
        title={t.system?.checkpointsPruneTitle ?? "Prune checkpoints"}
        description={t.system?.checkpointsPruneDescription ?? "Delete the rollback checkpoint shadow store? Existing /rollback points will be lost."}
        loading={checkpointsPrune.isDeleting}
      />
      <DeleteConfirmDialog
        open={hookDelete.isOpen}
        onCancel={hookDelete.cancel}
        onConfirm={hookDelete.confirm}
        title={t.system?.hookRemoveTitle ?? "Remove shell hook"}
        description={t.system?.hookRemoveDescription ?? "Remove this hook from config and revoke its consent? It stops firing on the next restart."}
        loading={hookDelete.isDeleting}
      />

      {/* Create-hook modal */}
      {hookModalOpen && (
        <div
          ref={hookModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setHookModalOpen(false)}
          role="dialog"
          aria-modal="true"
        >
          <div className={cn(themedBody, "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col")}>
            <Button
              ghost
              size="icon"
              onClick={() => setHookModalOpen(false)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label={t.system?.hookCloseAriaLabel ?? "Close"}
            >
              <X />
            </Button>
            <header className="p-5 pb-3 border-b border-border">
              <h2 className="font-mondwest text-display text-base tracking-wider">
                {t.system?.hookModalTitle ?? "New shell hook"}
              </h2>
            </header>
            <div className="p-5 grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="hook-event">{t.system?.hookEventLabel ?? "Event"}</Label>
                <Select
                  id="hook-event"
                  value={hookEvent}
                  onValueChange={(v) => setHookEvent(v)}
                >
                  {validEvents.map((ev) => (
                    <SelectOption key={ev} value={ev}>
                      {ev}
                    </SelectOption>
                  ))}
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="hook-command">{t.system?.hookCommandLabel ?? "Command (absolute path)"}</Label>
                <Input
                  id="hook-command"
                  autoFocus
                  placeholder={t.system?.hookCommandPlaceholder ?? "/usr/local/bin/my-hook.sh"}
                  value={hookCommand}
                  onChange={(e) => setHookCommand(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="hook-matcher">{t.system?.hookMatcherLabel ?? "Matcher (optional)"}</Label>
                  <Input
                    id="hook-matcher"
                    placeholder={t.system?.hookMatcherPlaceholder ?? "e.g. terminal"}
                    value={hookMatcher}
                    onChange={(e) => setHookMatcher(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="hook-timeout">{t.system?.hookTimeoutLabel ?? "Timeout (s)"}</Label>
                  <Input
                    id="hook-timeout"
                    placeholder={t.system?.hookTimeoutPlaceholder ?? "10"}
                    value={hookTimeout}
                    onChange={(e) => setHookTimeout(e.target.value)}
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={hookApprove}
                  onChange={(e) => setHookApprove(e.target.checked)}
                />
                {t.system?.hookApproveCheckbox ?? "Approve now (grant consent so it fires; otherwise it stays configured but inactive)"}
              </label>
              <p className="text-xs text-warning">
                {t.system?.hookWarning ?? "Shell hooks run arbitrary commands on this host. Only add scripts you trust. Takes effect on the next gateway/session restart."}
              </p>
              <div className="flex justify-end">
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={createHook}
                  disabled={creatingHook}
                  prefix={creatingHook ? <Spinner /> : undefined}
                >
                  {creatingHook
                    ? (t.system?.hookCreatingButton ?? "Creating")
                    : (t.system?.hookCreateButton ?? "Create hook")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Live action log */}
      {activeAction && (
        <ActionLogViewer
          action={activeAction}
          onClose={() => setActiveAction(null)}
        />
      )}

      {/* ── Host / system stats ───────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Server className="h-4 w-4" /> {t.system?.hostSectionTitle ?? "Host"}
        </H2>
        <Card>
          <CardContent className="py-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-3 gap-x-6 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelOs ?? "OS"}</div>
                <div>{stats?.os} {stats?.os_release}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelArch ?? "Arch"}</div>
                <div>{stats?.arch}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelHost ?? "Host"}</div>
                <div className="truncate">{stats?.hostname}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelPython ?? "Python"}</div>
                <div>{stats?.python_impl} {stats?.python_version}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelHermes ?? "Hermes"}</div>
                <div>v{stats?.hermes_version}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <Cpu className="h-3 w-3" /> {t.system?.hostLabelCpu ?? "CPU"}
                </div>
                <div>
                  {t.system?.hostCpuCores?.replace("{count}", String(stats?.cpu_count ?? "—")) ?? `${stats?.cpu_count ?? "—"} cores`}
                  {typeof stats?.cpu_percent === "number"
                    ? ` · ${stats.cpu_percent.toFixed(0)}%`
                    : ""}
                </div>
              </div>
              {stats?.memory && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelMemory ?? "Memory"}</div>
                  <div>
                    {formatBytes(stats.memory.used)} / {formatBytes(stats.memory.total)} ({stats.memory.percent}%)
                  </div>
                </div>
              )}
              {stats?.disk && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                    <HardDrive className="h-3 w-3" /> {t.system?.hostLabelDisk ?? "Disk"}
                  </div>
                  <div>
                    {formatBytes(stats.disk.used)} / {formatBytes(stats.disk.total)} ({stats.disk.percent}%)
                  </div>
                </div>
              )}
              {typeof stats?.uptime_seconds === "number" && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelUptime ?? "Uptime"}</div>
                  <div>{formatDuration(stats.uptime_seconds)}</div>
                </div>
              )}
              {stats?.load_avg && stats.load_avg.length >= 3 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t.system?.hostLabelLoadAvg ?? "Load avg"}</div>
                  <div>{stats.load_avg.map((n) => n.toFixed(2)).join(" / ")}</div>
                </div>
              )}
            </div>
            {stats && !stats.psutil && (
              <p className="mt-3 text-xs text-muted-foreground">
                {t.system?.hostPsutilHint ?? <>Install the <span className="font-mono">psutil</span> extra for CPU / memory / disk metrics.</>}
              </p>
            )}
          </CardContent>
        </Card>
      </section>

      {/* ── Curator ───────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Sparkles className="h-4 w-4" /> {t.system?.curatorSectionTitle ?? "Skill curator"}
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <Badge tone={curator?.paused ? "warning" : curator?.enabled ? "success" : "secondary"}>
                {curator?.paused
                  ? (t.system?.curatorStatusPaused ?? "paused")
                  : curator?.enabled
                    ? (t.system?.curatorStatusActive ?? "active")
                    : (t.system?.curatorStatusDisabled ?? "disabled")}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {curator?.interval_hours ? `every ${curator.interval_hours}h` : ""}
                {curator?.last_run_at
                  ? ` · last run ${new Date(curator.last_run_at).toLocaleString()}`
                  : ` ${t.system?.curatorNeverRun ?? "· never run"}`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" ghost onClick={toggleCuratorPaused}>
                {curator?.paused
                  ? (t.system?.curatorResume ?? "Resume")
                  : (t.system?.curatorPause ?? "Pause")}
              </Button>
              <Button
                size="sm"
                ghost
                prefix={<Play className="h-3.5 w-3.5" />}
                onClick={() => runOp(api.runCurator, "Curator review")}
              >
                {t.system?.curatorRunNow ?? "Run now"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Gateway ───────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Power className="h-4 w-4" /> {t.system?.gatewaySectionTitle ?? "Gateway"}
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <Badge tone={gatewayRunning ? "success" : "secondary"}>
                {gatewayRunning
                  ? (t.system?.gatewayRunning ?? "running")
                  : (t.system?.gatewayStopped ?? "stopped")}
              </Badge>
              <span className="text-sm text-muted-foreground tabular-nums">
                {gatewayStatusLabel}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                className="uppercase"
                onClick={() => runGateway("start")}
                disabled={gatewayRunning}
                prefix={<Play className="h-3.5 w-3.5" />}
              >
                {t.system?.gatewayStart ?? "Start"}
              </Button>
              <Button
                size="sm"
                className="uppercase"
                onClick={() => runGateway("restart")}
                prefix={<RotateCw className="h-3.5 w-3.5" />}
              >
                {t.system?.gatewayRestart ?? "Restart"}
              </Button>
              <Button
                size="sm"
                className="uppercase text-warning"
                ghost
                onClick={() => runGateway("stop")}
                disabled={!gatewayRunning}
                prefix={<Power className="h-3.5 w-3.5" />}
              >
                {t.system?.gatewayStop ?? "Stop"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Memory ────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Brain className="h-4 w-4" /> {t.system?.memorySectionTitle ?? "Memory"}
        </H2>
        <Card>
          <CardContent className="flex flex-col gap-4 py-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>
                {t.system?.memoryExternalProvider ?? "External provider:"}{" "}
                <span className="font-mono text-foreground">
                  {memory?.active || (t.system?.memoryBuiltinOnly ?? "built-in only")}
                </span>
              </span>
              <Link to="/plugins" className="underline">
                {t.system?.memoryChangeInPlugins ?? "Change in Plugins →"}
              </Link>
              <span className="ml-auto">
                {t.system?.memoryNewCredentials ?? "New credentials: hermes memory setup"}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
              <span className="text-xs text-muted-foreground">
                {t.system?.memoryBuiltinFiles
                  ?.replace("{memorySize}", formatBytes(memory?.builtin_files.memory ?? 0))
                  .replace("{userSize}", formatBytes(memory?.builtin_files.user ?? 0))
                  ?? `Built-in files — MEMORY.md: ${formatBytes(memory?.builtin_files.memory ?? 0)} · USER.md: ${formatBytes(memory?.builtin_files.user ?? 0)}`}
              </span>
              <div className="flex items-center gap-2 ml-auto">
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("memory")}>
                  {t.system?.memoryResetMemoryMd ?? "Reset MEMORY.md"}
                </Button>
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("user")}>
                  {t.system?.memoryResetUserMd ?? "Reset USER.md"}
                </Button>
                <Button size="sm" ghost className="text-destructive" onClick={() => memoryReset.requestDelete("all")}>
                  {t.system?.memoryResetAll ?? "Reset all"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Credential pool ───────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <KeyRound className="h-4 w-4" /> {t.system?.credPoolSectionTitle ?? "Credential pool"}
        </H2>
        <Card>
          <CardContent className="flex flex-col gap-4 py-4">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
              <div className="grid gap-2">
                <Label htmlFor="cred-provider">{t.system?.credProviderLabel ?? "Provider"}</Label>
                <Input id="cred-provider" value={credProvider} onChange={(e) => setCredProvider(e.target.value)} placeholder={t.system?.credProviderPlaceholder ?? "openrouter"} />
              </div>
              <div className="grid gap-2 sm:col-span-2">
                <Label htmlFor="cred-key">{t.system?.credApiKeyLabel ?? "API key"}</Label>
                <Input id="cred-key" type="password" value={credKey} onChange={(e) => setCredKey(e.target.value)} placeholder={t.system?.credApiKeyPlaceholder ?? "sk-…"} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cred-label">{t.system?.credLabelLabel ?? "Label"}</Label>
                <Input id="cred-label" value={credLabel} onChange={(e) => setCredLabel(e.target.value)} placeholder={t.system?.credLabelPlaceholder ?? "optional"} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button size="sm" className="uppercase" onClick={addCredential} disabled={addingCred} prefix={addingCred ? <Spinner /> : undefined}>
                {t.system?.credAddKey ?? "Add key"}
              </Button>
            </div>
            {pool.length === 0 && (
              <p className="text-sm text-muted-foreground">
                {t.system?.credNoPooled ?? "No pooled credentials. Add one above to enable key rotation."}
              </p>
            )}
            {pool.map((prov) => (
              <div key={prov.provider} className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  {prov.provider}
                </span>
                {prov.entries.map((entry) => (
                  <div key={`${prov.provider}-${entry.index}`} className="flex items-center gap-3 border border-border bg-background/40 px-3 py-2">
                    <span className="text-sm font-medium">{entry.label}</span>
                    <span className="font-mono text-xs text-muted-foreground">{entry.token_preview}</span>
                    <Badge tone="outline">{entry.auth_type}</Badge>
                    {entry.last_status && <Badge tone="secondary">{entry.last_status}</Badge>}
                    <Button ghost size="icon" className="ml-auto text-destructive" aria-label={t.system?.credRemoveAriaLabel ?? "Remove credential"} onClick={() => credDelete.requestDelete(`${prov.provider}|${entry.index}`)}>
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      {/* ── Operations ────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Activity className="h-4 w-4" /> {t.system?.opsSectionTitle ?? "Operations"}
        </H2>
        <Card>
          <CardContent className="flex flex-wrap gap-2 py-4">
            <Button size="sm" ghost prefix={<Stethoscope className="h-3.5 w-3.5" />} onClick={() => runOp(api.runDoctor, "Doctor")}>
              {t.system?.opsRunDoctor ?? "Run doctor"}
            </Button>
            <Button size="sm" ghost prefix={<ShieldCheck className="h-3.5 w-3.5" />} onClick={() => runOp(api.runSecurityAudit, "Security audit")}>
              {t.system?.opsSecurityAudit ?? "Security audit"}
            </Button>
            <Button size="sm" ghost prefix={<Database className="h-3.5 w-3.5" />} onClick={() => runOp(() => api.runBackup(), "Backup")}>
              {t.system?.opsCreateBackup ?? "Create backup"}
            </Button>
            <Button size="sm" ghost prefix={<RotateCw className="h-3.5 w-3.5" />} onClick={() => runOp(api.updateSkillsFromHub, "Skills update")}>
              {t.system?.opsUpdateSkills ?? "Update skills"}
            </Button>
            <Button size="sm" ghost prefix={<Activity className="h-3.5 w-3.5" />} onClick={() => runOp(api.runPromptSize, "Prompt size")}>
              {t.system?.opsPromptSize ?? "Prompt size"}
            </Button>
            <Button size="sm" ghost prefix={<Database className="h-3.5 w-3.5" />} onClick={() => runOp(api.runDump, "Support dump")}>
              {t.system?.opsSupportDump ?? "Support dump"}
            </Button>
            <Button size="sm" ghost prefix={<RotateCw className="h-3.5 w-3.5" />} onClick={() => runOp(api.runConfigMigrate, "Config migrate")}>
              {t.system?.opsMigrateConfig ?? "Migrate config"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-end">
            <div className="grid gap-2 flex-1">
              <Label htmlFor="import-path">{t.system?.importLabel ?? "Restore from backup archive"}</Label>
              <Input id="import-path" value={importPath} onChange={(e) => setImportPath(e.target.value)} placeholder={t.system?.importPlaceholder ?? "/path/to/hermes-backup.zip"} />
            </div>
            <Button
              size="sm"
              ghost
              disabled={!importPath.trim()}
              onClick={() => {
                if (!importPath.trim()) return;
                setImportConfirmOpen(true);
              }}
            >
              {t.system?.importButton ?? "Import"}
            </Button>
            <ConfirmDialog
              open={importConfirmOpen}
              title={t.system?.importConfirmTitle ?? "Restore from backup?"}
              description={
                t.system?.importConfirmDescription?.replace("{archive}", importPath.trim() || "the archive")
                ?? `This will overwrite your current Hermes configuration, skills, sessions, and data with the contents of ${importPath.trim() || "the archive"}. This cannot be undone.`
              }
              destructive
              confirmLabel={t.system?.importConfirmLabel ?? "Restore"}
              cancelLabel={t.system?.importCancelLabel ?? "Cancel"}
              onCancel={() => setImportConfirmOpen(false)}
              onConfirm={() => {
                setImportConfirmOpen(false);
                runOp(() => api.runImport(importPath.trim(), true), "Import");
              }}
            />
          </CardContent>
        </Card>
      </section>

      {/* ── Checkpoints ───────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
          <Database className="h-4 w-4" /> {t.system?.checkpointsSectionTitle ?? "Checkpoints"}
        </H2>
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <span className="text-sm text-muted-foreground">
              {t.system?.checkpointsSessions
                ?.replace("{count}", String(checkpoints?.sessions.length ?? 0))
                .replace("{size}", formatBytes(checkpoints?.total_bytes ?? 0))
                ?? `${checkpoints?.sessions.length ?? 0} session(s) · ${formatBytes(checkpoints?.total_bytes ?? 0)}`}
            </span>
            <Button size="sm" ghost className="text-destructive" disabled={!checkpoints?.sessions.length} prefix={<Trash2 className="h-3.5 w-3.5" />} onClick={() => checkpointsPrune.requestDelete("all")}>
              {t.system?.checkpointsPrune ?? "Prune"}
            </Button>
          </CardContent>
        </Card>
      </section>

      {/* ── Shell hooks ───────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <H2 variant="sm" className="flex items-center gap-2 text-muted-foreground">
            <Terminal className="h-4 w-4" /> {t.system?.hooksSectionTitle ?? "Shell hooks"}
          </H2>
          <Button size="sm" className="uppercase" prefix={<Plus className="h-3.5 w-3.5" />} onClick={() => setHookModalOpen(true)}>
            {t.system?.hooksNewHook ?? "New hook"}
          </Button>
        </div>
        {(!hooks || hooks.hooks.length === 0) && (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              {t.system?.hooksNoneConfigured ?? "No shell hooks configured."}
            </CardContent>
          </Card>
        )}
        {hooks?.hooks.map((h: HookEntry, i) => (
          <Card key={`${h.event}-${i}`}>
            <CardContent className="flex items-center gap-3 py-3">
              <Badge tone="outline">{h.event}</Badge>
              {h.matcher && (
                <span className="text-xs text-muted-foreground">
                  {t.system?.hooksMatcher?.replace("{matcher}", h.matcher) ?? `matcher: ${h.matcher}`}
                </span>
              )}
              <span className="font-mono text-xs truncate flex-1">{h.command}</span>
              {h.executable === false && (
                <Badge tone="destructive">{t.system?.hooksNotExecutable ?? "not executable"}</Badge>
              )}
              <Badge tone={h.allowed ? "success" : "warning"}>
                {h.allowed
                  ? (t.system?.hooksAllowed ?? "allowed")
                  : (t.system?.hooksNotApproved ?? "not approved")}
              </Badge>
              <Button
                ghost
                size="icon"
                className="text-destructive"
                aria-label={t.system?.hooksRemoveAriaLabel ?? "Remove hook"}
                onClick={() =>
                  hookDelete.requestDelete(`${h.event}|${h.command ?? ""}`)
                }
              >
                <Trash2 />
              </Button>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
