import { useCallback, useEffect, useLayoutEffect, useMemo, useState, Fragment, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ExternalLink,
  PlugZap,
  QrCode,
  Radio,
  RotateCw,
  Save,
  Settings2,
  WifiOff,
  X,
} from "lucide-react";
import * as QRCode from "qrcode";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { api } from "@/lib/api";
import type {
  MessagingPlatform,
  MessagingPlatformEnvVar,
  MessagingPlatformUpdate,
  TelegramOnboardingStartResponse,
} from "@/lib/api";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn, themedBody, hubPanelTitle, hubInlineCode, GATEWAY_START_CMD } from "@/lib/utils";
import { useI18n } from "@/i18n";
import type { Translations } from "@/i18n/types";
import { ClawbotOnboardingPanel } from "@/pages/ClawbotChannelPanel";
import { WecomChannelPanel } from "@/pages/WecomChannelPanel";
import {
  resolvePlatformConnectionState,
  type ConnectionState,
} from "@/lib/channelConnection";

function resolvePlatformDisplay(
  platform: Pick<MessagingPlatform, "id" | "name" | "description">,
  t: Translations,
) {
  const label = t.channels?.platformLabels?.[platform.id];
  return {
    name: label?.name ?? platform.name,
    description: label?.description ?? platform.description,
  };
}

function resolveEnvFieldLabel(
  field: Pick<MessagingPlatformEnvVar, "key" | "prompt" | "description">,
  t: Translations,
) {
  const localized = t.channels?.envFieldLabels?.[field.key];
  return {
    prompt: localized?.prompt ?? field.prompt ?? field.key,
    description: localized?.description ?? field.description,
  };
}

// State → badge mapping. The backend emits a small, fixed vocabulary plus
// whatever the live gateway runtime reports (connected/disconnected/fatal).
function InlineCommand({ children }: { children: string }) {
  return <code className={hubInlineCode}>{children}</code>;
}

function highlightCommand(text: string, cmd: string): ReactNode {
  if (!text.includes(cmd)) return text;
  const parts = text.split(cmd);
  return parts.map((part, i) => (
    <Fragment key={i}>
      {part}
      {i < parts.length - 1 ? <InlineCommand>{cmd}</InlineCommand> : null}
    </Fragment>
  ));
}

function GatewayNotRunningNotice({
  message,
}: {
  message: string | undefined;
}) {
  if (message) {
    return <>{highlightCommand(message, GATEWAY_START_CMD)}</>;
  }
  return (
    <>
      The gateway is not running. Configure channels here, then start the
      gateway with <InlineCommand>{GATEWAY_START_CMD}</InlineCommand> (or the
      Restart button above).
    </>
  );
}

const STATE_BADGE: Record<
  string,
  { tone: "success" | "warning" | "destructive" | "secondary" | "outline"; key: string }
> = {
  disabled: { tone: "secondary", key: "stateDisabled" },
  not_enabled: { tone: "outline", key: "stateNotEnabled" },
  enabled: { tone: "success", key: "stateEnabled" },
};

const CONNECTION_BADGE: Record<
  ConnectionState,
  { tone: "success" | "warning" | "destructive" | "secondary" | "outline"; key: string }
> = {
  connected: { tone: "success", key: "connConnected" },
  connecting: { tone: "warning", key: "connConnecting" },
  disconnected: { tone: "warning", key: "connDisconnected" },
  gateway_stopped: { tone: "warning", key: "connGatewayStopped" },
  error: { tone: "destructive", key: "connError" },
  paused: { tone: "secondary", key: "connPaused" },
};

function normalizeChannelState(
  state: string,
  platform: Pick<MessagingPlatform, "enabled" | "configured">,
): keyof typeof STATE_BADGE {
  if (state in STATE_BADGE) return state as keyof typeof STATE_BADGE;
  if (!platform.enabled) return "disabled";
  if (!platform.configured) return "not_enabled";
  return "enabled";
}

const TELEGRAM_USER_ID_RE = /^\d+$/;

function formatExpiry(expiresAt: string): string {
  const ms = Date.parse(expiresAt) - Date.now();
  if (!Number.isFinite(ms) || ms <= 0) return "expired";
  const seconds = Math.ceil(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

function isTerminalTelegramOnboardingError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /\b410\b/.test(message) && /\b(expired|claimed|gone)\b/i.test(message);
}

export default function ChannelsPage() {
  const { t } = useI18n();
  const [platforms, setPlatforms] = useState<MessagingPlatform[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast, showToast } = useToast();
  const { setEnd } = usePageHeader();

  // Config modal state
  const [editing, setEditing] = useState<MessagingPlatform | null>(null);
  const [draftEnv, setDraftEnv] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const closeEdit = useCallback(() => setEditing(null), []);
  const editModalRef = useModalBehavior({ open: editing !== null, onClose: closeEdit });

  // Per-card busy + restart-needed tracking
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const gatewayRunning = platforms.length > 0 && platforms[0].gateway_running;

  const load = useCallback(() => {
    return api
      .getMessagingPlatforms()
      .then((res) => setPlatforms(res.platforms))
      .catch((e) => showToast(`Error: ${e}`, "error"));
  }, [showToast]);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    const needsPoll = platforms.some((p) => {
      const conn = resolvePlatformConnectionState(p);
      return (
        p.enabled &&
        p.configured &&
        (conn === "connecting" || conn === "disconnected")
      );
    });
    if (!needsPoll) return;
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [platforms, load]);

  const openConfig = (platform: MessagingPlatform) => {
    const initial: Record<string, string> = {};
    platform.env_vars.forEach((v) => {
      initial[v.key] = "";
    });
    setDraftEnv(initial);
    setEditing(platform);
  };

  const handleSave = async () => {
    if (!editing) return;
    // Only send fields the user actually filled in — leaving a field blank
    // preserves the existing value rather than clobbering it.
    const env: Record<string, string> = {};
    Object.entries(draftEnv).forEach(([k, v]) => {
      if (v.trim()) env[k] = v.trim();
    });
    if (Object.keys(env).length === 0) {
      showToast(t.channels?.nothingToSave ?? "Nothing to save — fill in at least one field.", "error");
      return;
    }
    const missing = editing.env_vars.filter(
      (v) => v.required && !v.is_set && !env[v.key],
    );
    if (missing.length > 0) {
      const fieldName = missing[0].prompt || missing[0].key;
      showToast(
        t.channels?.fieldRequired?.replace("{field}", fieldName) ?? `${fieldName} is required`,
        "error",
      );
      return;
    }
    setSaving(true);
    try {
      const body: MessagingPlatformUpdate = { env, enabled: true };
      await api.updateMessagingPlatform(editing.id, body);
      const editingLabel = resolvePlatformDisplay(editing, t).name;
      showToast(
        t.channels?.platformSaved?.replace("{name}", editingLabel) ?? `${editingLabel} saved`,
        "success",
      );
      setEditing(null);
      setRestartNeeded(true);
      await load();
    } catch (e) {
      showToast(
        t.channels?.failedToSave?.replace("{error}", String(e)) ?? `Failed to save: ${e}`,
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (platform: MessagingPlatform) => {
    const next = !platform.enabled;
    setTogglingId(platform.id);
    try {
      await api.updateMessagingPlatform(platform.id, { enabled: next });
      setPlatforms((prev) =>
        prev.map((p) =>
          p.id === platform.id
            ? {
                ...p,
                enabled: next,
                state: next ? (p.configured ? "enabled" : "not_enabled") : "disabled",
              }
            : p,
        ),
      );
      setRestartNeeded(true);
    } catch (e) {
      showToast(`Error: ${e}`, "error");
    } finally {
      setTogglingId(null);
    }
  };

  const handleTest = async (platform: MessagingPlatform) => {
    setTestingId(platform.id);
    try {
      const res = await api.testMessagingPlatform(platform.id);
      const platformLabel = resolvePlatformDisplay(platform, t).name;
      showToast(`${platformLabel}: ${res.message}`, res.ok ? "success" : "error");
    } catch (e) {
      showToast(`Error: ${e}`, "error");
    } finally {
      setTestingId(null);
    }
  };

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await api.restartGateway();
      showToast(t.channels?.gatewayRestarting ?? "Gateway restarting…", "success");
      setRestartNeeded(false);
      // Give the gateway a moment to come up, then refresh status.
      setTimeout(() => void load(), 4000);
    } catch (e) {
      showToast(
        t.channels?.failedToRestart?.replace("{error}", String(e)) ?? `Failed to restart: ${e}`,
        "error",
      );
    } finally {
      setRestarting(false);
    }
  };

  useLayoutEffect(() => {
    setEnd(
      <Button
        className="uppercase"
        size="sm"
        onClick={handleRestart}
        disabled={restarting}
        prefix={restarting ? <Spinner /> : <RotateCw className="h-4 w-4" />}
      >
        {restarting
          ? (t.channels?.restarting ?? "Restarting…")
          : (t.channels?.restartGateway ?? "Restart gateway")}
      </Button>,
    );
    return () => setEnd(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setEnd, restarting]);

  const configured = useMemo(
    () => platforms.filter((p) => p.configured).length,
    [platforms],
  );

  // Build a stateBadge helper that uses translated labels
  const stateBadge = (platform: MessagingPlatform) => {
    const state = normalizeChannelState(platform.state, platform);
    const entry = STATE_BADGE[state];
    const label =
      ((t.channels as Record<string, string> | undefined)?.[entry.key] ?? state);
    return { tone: entry.tone, label };
  };

  const connectionBadge = (platform: MessagingPlatform) => {
    const conn = resolvePlatformConnectionState(platform);
    if (!conn) return null;
    const entry = CONNECTION_BADGE[conn];
    const label =
      ((t.channels as Record<string, string> | undefined)?.[entry.key] ?? conn);
    return { tone: entry.tone, label };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Toast toast={toast} />

      {/* Restart banner */}
      {restartNeeded && (
        <Card className="border-warning/50">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm">
              <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
              <span>
                {t.channels?.restartBannerMessage ?? "Changes are saved. Restart the gateway for them to take effect."}
              </span>
            </div>
            <Button
              size="sm"
              className="uppercase shrink-0"
              onClick={handleRestart}
              disabled={restarting}
              prefix={restarting ? <Spinner /> : <RotateCw className="h-4 w-4" />}
            >
              {restarting
                ? (t.channels?.restarting ?? "Restarting…")
                : (t.channels?.restartNow ?? "Restart now")}
            </Button>
          </CardContent>
        </Card>
      )}

      {!gatewayRunning && !restartNeeded && (
        <Card className="border-border">
          <CardContent className="flex items-start gap-2 p-4 font-sans text-sm leading-relaxed text-muted-foreground">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0" />
            <GatewayNotRunningNotice message={t.channels?.gatewayNotRunningMessage} />
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        {t.channels?.channelsSummary
          ?.replace("{configured}", String(configured))
          ?.replace("{total}", String(platforms.length))
          ?? `${configured} of ${platforms.length} channels configured. Credentials are written to ~/.hermes/.env; the gateway connects each enabled channel on its next restart.`}
      </p>

      {/* Config modal */}
      {editing && (() => {
        const editingDisplay = resolvePlatformDisplay(editing, t);
        return (
        <div
          ref={editModalRef}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
          onClick={(e) => e.target === e.currentTarget && setEditing(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="channel-config-title"
        >
          <div
            className={cn(
              themedBody,
              "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col max-h-[90vh]",
            )}
          >
            <Button
              ghost
              size="icon"
              onClick={() => setEditing(null)}
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              aria-label={t.channels?.closeAriaLabel ?? "Close"}
            >
              <X />
            </Button>

            <header className="p-5 pb-3 border-b border-border">
              <h2
                id="channel-config-title"
                className={hubPanelTitle}
              >
                {t.channels?.configureTitle?.replace("{name}", editingDisplay.name) ?? `Configure ${editingDisplay.name}`}
              </h2>
              {editing.docs_url && (
                <a
                  href={editing.docs_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  {t.channels?.setupGuide ?? "Setup guide"} <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </header>

            <div className="p-5 grid gap-4 overflow-y-auto">
              <p className="text-xs text-muted-foreground">
                {editingDisplay.description}
              </p>
              {editing.env_vars.map((field: MessagingPlatformEnvVar) => {
                const fieldLabel = resolveEnvFieldLabel(field, t);
                return (
                <div className="grid gap-1.5" key={field.key}>
                  <Label htmlFor={`field-${field.key}`}>
                    {fieldLabel.prompt}
                    {field.required ? (t.channels?.requiredSuffix ?? " *") : ""}
                  </Label>
                  {fieldLabel.description && (
                    <span className="text-xs text-muted-foreground">
                      {fieldLabel.description}
                    </span>
                  )}
                  <Input
                    id={`field-${field.key}`}
                    type={field.is_password ? "password" : "text"}
                    placeholder={
                      field.is_set
                        ? field.redacted_value || (t.channels?.placeholderAlreadySet ?? "•••••• (set — leave blank to keep)")
                        : field.key
                    }
                    value={draftEnv[field.key] ?? ""}
                    onChange={(e) =>
                      setDraftEnv((prev) => ({ ...prev, [field.key]: e.target.value }))
                    }
                  />
                </div>
                );
              })}

              <div className="flex justify-end gap-2 pt-1">
                <Button ghost size="sm" onClick={() => setEditing(null)}>
                  {t.channels?.cancel ?? "Cancel"}
                </Button>
                <Button
                  className="uppercase"
                  size="sm"
                  onClick={handleSave}
                  disabled={saving}
                  prefix={saving ? <Spinner /> : undefined}
                >
                  {saving
                    ? (t.channels?.saving ?? "Saving…")
                    : (t.channels?.saveAndEnable ?? "Save & enable")}
                </Button>
              </div>
            </div>
          </div>
        </div>
        );
      })()}

      {/* Platform list */}
      <div className="grid gap-3">
        {platforms.map((platform) => {
          const badge = stateBadge(platform);
          const connBadge = connectionBadge(platform);
          const channelState = normalizeChannelState(platform.state, platform);
          const busy = togglingId === platform.id;
          const display = resolvePlatformDisplay(platform, t);
          const conn = resolvePlatformConnectionState(platform);
          const StateIcon =
            channelState !== "enabled"
              ? channelState === "disabled"
                ? WifiOff
                : Radio
              : conn === "connected"
                ? CheckCircle2
                : conn === "error"
                  ? AlertTriangle
                  : conn === "connecting"
                    ? Radio
                    : conn === "gateway_stopped" || conn === "disconnected"
                      ? WifiOff
                      : CheckCircle2;
          return (
            <Card key={platform.id} className="border-border">
              <CardContent className="flex flex-col gap-4 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3 min-w-0">
                    <StateIcon
                      className={cn(
                        "h-5 w-5 shrink-0 mt-0.5",
                        channelState === "enabled" && conn === "connected"
                          ? "text-success"
                          : channelState === "enabled" && conn === "error"
                            ? "text-destructive"
                            : channelState === "enabled" && conn === "connecting"
                              ? "text-warning"
                              : "text-muted-foreground",
                      )}
                    />
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-sans text-sm font-medium">
                          {display.name}
                        </span>
                        <Badge tone={badge.tone}>{badge.label}</Badge>
                        {connBadge && (
                          <Badge tone={connBadge.tone}>{connBadge.label}</Badge>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {display.description}
                      </span>
                      {platform.error_message && (
                        <span className="text-xs text-destructive">
                          {platform.error_message}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-start sm:self-center">
                    <div className="flex items-center gap-1.5">
                      {busy ? (
                        <Spinner className="text-sm" />
                      ) : (
                        <Switch
                          checked={platform.enabled}
                          onCheckedChange={() => void handleToggle(platform)}
                          aria-label={
                            t.channels?.enableAriaLabel?.replace("{name}", display.name)
                            ?? `Enable ${display.name}`
                          }
                        />
                      )}
                    </div>
                    <Button
                      ghost
                      size="sm"
                      onClick={() => handleTest(platform)}
                      disabled={testingId === platform.id}
                      prefix={
                        testingId === platform.id ? (
                          <Spinner />
                        ) : (
                          <PlugZap className="h-4 w-4" />
                        )
                      }
                    >
                      {t.channels?.test ?? "Test"}
                    </Button>
                    {platform.id !== "clawbot" && platform.id !== "wecom" && (
                    <Button
                      size="sm"
                      className="uppercase"
                      onClick={() => openConfig(platform)}
                      prefix={<Settings2 className="h-4 w-4" />}
                    >
                      {t.channels?.configure ?? "Configure"}
                    </Button>
                    )}
                  </div>
                </div>
                {platform.id === "wecom" && (
                  <WecomChannelPanel
                    onChanged={load}
                    onRestartNeeded={() => setRestartNeeded(true)}
                    platform={platform}
                    showToast={showToast}
                  />
                )}
                {platform.id === "clawbot" && (
                  <ClawbotOnboardingPanel
                    onChanged={load}
                    platform={platform}
                    showToast={showToast}
                  />
                )}
                {platform.id === "telegram" && (
                  <TelegramOnboardingPanel
                    onChanged={load}
                    onRestartNeeded={() => setRestartNeeded(true)}
                    platform={platform}
                    setRestartNeeded={setRestartNeeded}
                    showToast={showToast}
                  />
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function TelegramOnboardingPanel({
  onChanged,
  onRestartNeeded,
  platform,
  setRestartNeeded,
  showToast,
}: {
  onChanged: () => Promise<void>;
  onRestartNeeded: () => void;
  platform: MessagingPlatform;
  setRestartNeeded: (needed: boolean) => void;
  showToast: (message: string, type: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [setup, setSetup] = useState<TelegramOnboardingStartResponse | null>(
    null,
  );
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [phase, setPhase] = useState<
    "idle" | "starting" | "waiting" | "ready" | "applying"
  >("idle");
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const [allowedIds, setAllowedIds] = useState<string[]>([]);
  const [detectedOwnerId, setDetectedOwnerId] = useState<string | null>(null);
  const [newAllowedId, setNewAllowedId] = useState("");
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!setup || phase !== "waiting") return;
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const status = await api.getTelegramOnboardingStatus(setup.pairing_id);
        if (cancelled) return;
        if (status.status === "ready") {
          setPhase("ready");
          setBotUsername(status.bot_username ?? null);
          setError("");
          if (
            status.owner_user_id &&
            TELEGRAM_USER_ID_RE.test(status.owner_user_id)
          ) {
            setDetectedOwnerId(status.owner_user_id);
            setAllowedIds([status.owner_user_id]);
          }
          return;
        }
        setError("");
        timeout = setTimeout(poll, 2000);
      } catch (pollError) {
        if (cancelled) return;

        const expiresAt = Date.parse(setup.expires_at);
        const expired =
          Number.isFinite(expiresAt) && Date.now() >= expiresAt;
        if (isTerminalTelegramOnboardingError(pollError) || expired) {
          setSetup(null);
          setQrDataUrl("");
          setPhase("idle");
          setError(t.channels?.telegramPairingExpired ?? "Telegram pairing expired. Start a new QR setup to try again.");
          return;
        }

        setError(
          t.channels?.telegramStillWaiting?.replace("{error}", String(pollError))
          ?? `Still waiting for Telegram. Retrying after: ${pollError}`
        );
        timeout = setTimeout(poll, 2000);
      }
    };

    timeout = setTimeout(poll, 1200);
    return () => {
      cancelled = true;
      if (timeout) clearTimeout(timeout);
    };
  }, [phase, setup, t]);

  useEffect(() => {
    if (!setup) return;
    const timer = setInterval(() => setTick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [setup]);

  const resetSetup = () => {
    setSetup(null);
    setQrDataUrl("");
    setPhase("idle");
    setBotUsername(null);
    setAllowedIds([]);
    setDetectedOwnerId(null);
    setNewAllowedId("");
    setError("");
  };

  const start = async () => {
    setPhase("starting");
    setError("");
    setBotUsername(null);
    setAllowedIds([]);
    setDetectedOwnerId(null);
    setNewAllowedId("");
    try {
      const res = await api.startTelegramOnboarding({ bot_name: "Hermes Agent" });
      const dataUrl = await QRCode.toDataURL(res.qr_payload, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 224,
      });
      setSetup(res);
      setQrDataUrl(dataUrl);
      setPhase("waiting");
    } catch (startError) {
      setPhase("idle");
      setError(String(startError));
    }
  };

  const cancel = async () => {
    if (setup) {
      try {
        await api.cancelTelegramOnboarding(setup.pairing_id);
      } catch {
        /* local cleanup still wins */
      }
    }
    resetSetup();
  };

  const addAllowedId = () => {
    const trimmed = newAllowedId.trim();
    if (!TELEGRAM_USER_ID_RE.test(trimmed)) {
      setError(t.channels?.allowedIdsNumericError ?? "Allowed Telegram user IDs must be numeric.");
      return;
    }
    setError("");
    setAllowedIds((ids) => (ids.includes(trimmed) ? ids : [...ids, trimmed]));
    setNewAllowedId("");
  };

  // restart_started only means the `hermes gateway restart` child spawned —
  // not that the restart will succeed (e.g. systemd linger missing, service
  // manager failure). Poll the action status briefly and surface a non-zero
  // exit via the manual-restart banner. Note: in no-service installs the
  // child becomes the foreground gateway and never exits, so "still running
  // when the window closes" counts as success.
  const watchRestartOutcome = async () => {
    for (let i = 0; i < 20; i++) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      try {
        const st = await api.getActionStatus("gateway-restart", 5);
        if (st.running) continue;
        if (st.exit_code !== 0 && st.exit_code !== null) {
          onRestartNeeded();
          showToast(
            t.channels?.gatewayRestartFailed?.replace("{code}", String(st.exit_code))
            ?? `Gateway restart failed (exit ${st.exit_code}) — restart manually`,
            "error",
          );
        }
        return;
      } catch {
        // transient fetch error; keep polling
      }
    }
  };

  const apply = async () => {
    if (!setup) return;
    if (allowedIds.length === 0) {
      setError(t.channels?.addAtLeastOneId ?? "Add at least one allowed Telegram user ID.");
      return;
    }
    setPhase("applying");
    setError("");
    try {
      const result = await api.applyTelegramOnboarding(setup.pairing_id, {
        allowed_user_ids: allowedIds,
      });
      resetSetup();
      if (result.restart_started) {
        showToast(t.channels?.telegramSavedRestarting ?? "Telegram saved; gateway restarting…", "success");
        setRestartNeeded(false);
        setTimeout(() => void onChanged(), 4000);
        void watchRestartOutcome();
      } else if (result.restart_started === undefined && result.needs_restart) {
        try {
          await api.restartGateway();
          showToast(t.channels?.telegramSavedRestarting ?? "Telegram saved; gateway restarting…", "success");
          setRestartNeeded(false);
          setTimeout(() => void onChanged(), 4000);
        } catch (restartError) {
          onRestartNeeded();
          showToast(
            t.channels?.telegramSavedRestartFailed?.replace("{error}", String(restartError))
            ?? `Telegram saved; gateway restart failed: ${restartError}`,
            "error",
          );
        }
      } else {
        onRestartNeeded();
        const detail = result.restart_error ? `: ${result.restart_error}` : "";
        showToast(
          t.channels?.telegramSavedRestartFailedDetail?.replace("{detail}", detail)
          ?? `Telegram saved; gateway restart failed${detail}`,
          "error",
        );
      }
      await onChanged();
    } catch (applyError) {
      setPhase("ready");
      setError(String(applyError));
    }
  };

  const expiresIn = useMemo(
    () => (setup ? formatExpiry(setup.expires_at) : ""),
    // tick keeps the memo fresh without recalculating on every render branch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setup, tick],
  );

  const expiresInLabel = expiresIn === "expired"
    ? (t.channels?.expired ?? "expired")
    : expiresIn;

  return (
    <div className="rounded-sm border border-border bg-background/35 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          className="uppercase"
          onClick={() => void start()}
          disabled={phase === "starting" || phase === "waiting" || phase === "applying"}
          prefix={phase === "starting" ? <Spinner /> : <QrCode className="h-4 w-4" />}
        >
          {phase === "starting"
            ? (t.channels?.starting ?? "Starting…")
            : (t.channels?.setUpWithQr ?? "Set up with QR")}
        </Button>
        {platform.configured && (
          <span className="text-xs text-muted-foreground">
            {t.channels?.existingCredentials ?? "Existing Telegram credentials are configured."}
          </span>
        )}
      </div>

      {error && (
        <div className="mt-3 border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {setup && qrDataUrl && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div className="grid gap-3">
            {(phase === "ready" || phase === "applying") && (
              <div className="grid gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="success">{t.channels?.readyBadge ?? "Ready"}</Badge>
                  {botUsername && (
                    <span className="font-mono-ui text-sm text-muted-foreground">
                      @{botUsername}
                    </span>
                  )}
                </div>

                <div className="grid gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
                      {t.channels?.allowedUsers ?? "Allowed users"}
                    </span>
                    {detectedOwnerId && allowedIds.includes(detectedOwnerId) && (
                      <Badge tone="success">{t.channels?.ownerDetected ?? "owner detected"}</Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {allowedIds.map((id) => (
                      <button
                        key={id}
                        type="button"
                        className="inline-flex items-center gap-1 border border-border px-2 py-1 font-mono-ui text-xs text-foreground hover:border-destructive/50"
                        onClick={() =>
                          setAllowedIds((ids) =>
                            ids.filter((existing) => existing !== id),
                          )
                        }
                      >
                        {id}
                        <X className="h-3 w-3" />
                      </button>
                    ))}
                    {allowedIds.length === 0 && (
                      <span className="text-sm text-muted-foreground">
                        {t.channels?.addAtLeastOneIdHint ?? "Add at least one Telegram user ID."}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={newAllowedId}
                    onChange={(event) => setNewAllowedId(event.target.value)}
                    placeholder={t.channels?.telegramUserIdPlaceholder ?? "Telegram user ID"}
                    className="font-mono-ui"
                  />
                  <Button size="sm" outlined onClick={addAllowedId} prefix={<Check />}>
                    {t.channels?.add ?? "Add"}
                  </Button>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    className="uppercase"
                    onClick={() => void apply()}
                    disabled={phase === "applying"}
                    prefix={phase === "applying" ? <Spinner /> : <Save className="h-4 w-4" />}
                  >
                    {phase === "applying"
                      ? (t.channels?.saving ?? "Saving…")
                      : (t.channels?.saveAndRestart ?? "Save and restart")}
                  </Button>
                  <Button size="sm" ghost onClick={() => void cancel()}>
                    {t.channels?.cancel ?? "Cancel"}
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col items-center justify-center gap-3">
            <img
              src={qrDataUrl}
              alt={t.channels?.qrCodeAlt ?? "Telegram setup QR code"}
              className="h-56 w-56 bg-white p-2"
            />
            <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
              <Badge tone={expiresIn === "expired" ? "destructive" : "outline"}>
                {expiresInLabel}
              </Badge>
              {phase === "waiting" && (
                <Badge tone="warning">{t.channels?.waitingBadge ?? "waiting"}</Badge>
              )}
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              <a
                href={setup.deep_link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1 border border-border px-3 text-xs uppercase text-foreground hover:border-foreground/40"
              >
                <ExternalLink className="h-4 w-4" />
                {t.channels?.openTelegram ?? "Open Telegram"}
              </a>
              <Button size="sm" ghost onClick={() => void cancel()}>
                {t.channels?.cancel ?? "Cancel"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
