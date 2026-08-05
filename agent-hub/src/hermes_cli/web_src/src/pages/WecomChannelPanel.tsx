import { useEffect, useMemo, useState } from "react";
import { Save, ShieldAlert } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api } from "@/lib/api";
import type { MessagingPlatform, WecomPlatformExtra } from "@/lib/api";
import { useI18n } from "@/i18n";

function envVar(platform: MessagingPlatform, key: string) {
  return platform.env_vars.find((v) => v.key === key);
}

export function WecomChannelPanel({
  platform,
  onChanged,
  onRestartNeeded,
  showToast,
}: {
  platform: MessagingPlatform;
  onChanged: () => Promise<void>;
  onRestartNeeded: () => void;
  showToast: (message: string, type: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const mx = t.channels?.wecom;
  const extra = (platform.platform_extra ?? {}) as WecomPlatformExtra;

  const [botId, setBotId] = useState("");
  const [secret, setSecret] = useState("");
  const [websocketUrl, setWebsocketUrl] = useState("");
  const [welcome, setWelcome] = useState(extra.welcome ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const cfg = (platform.platform_extra ?? {}) as WecomPlatformExtra;
    setWelcome(cfg.welcome ?? "");
    setBotId("");
    setSecret("");
    setWebsocketUrl("");
  }, [platform.platform_extra, platform.env_vars]);

  const botField = useMemo(() => envVar(platform, "WECOM_BOT_ID"), [platform]);
  const secretField = useMemo(() => envVar(platform, "WECOM_SECRET"), [platform]);
  const wsField = useMemo(() => envVar(platform, "WECOM_WEBSOCKET_URL"), [platform]);

  const fieldLabel = (key: string, fallback: string) =>
    t.channels?.envFieldLabels?.[key]?.prompt ?? fallback;

  const placeholderSet =
    t.channels?.placeholderAlreadySet ?? "•••••• (set — leave blank to keep)";

  const save = async () => {
    const botReady = Boolean(botId.trim() || botField?.is_set);
    const secretReady = Boolean(secret.trim() || secretField?.is_set);
    if (!botReady) {
      showToast(
        t.channels?.fieldRequired?.replace("{field}", fieldLabel("WECOM_BOT_ID", "Bot ID")) ??
          "Bot ID is required",
        "error",
      );
      return;
    }
    if (!secretReady) {
      showToast(
        t.channels?.fieldRequired?.replace("{field}", fieldLabel("WECOM_SECRET", "Secret")) ??
          "Secret is required",
        "error",
      );
      return;
    }

    const env: Record<string, string> = {};
    if (botId.trim()) env.WECOM_BOT_ID = botId.trim();
    if (secret.trim()) env.WECOM_SECRET = secret.trim();
    if (websocketUrl.trim()) env.WECOM_WEBSOCKET_URL = websocketUrl.trim();

    setSaving(true);
    try {
      await api.updateMessagingPlatform(platform.id, {
        env,
        extra: { welcome },
      });
      showToast(
        t.channels?.platformSaved?.replace(
          "{name}",
          t.channels?.platformLabels?.wecom?.name ?? platform.name,
        ) ?? "WeCom saved",
        "success",
      );
      onRestartNeeded();
      await onChanged();
    } catch (e) {
      showToast(
        t.channels?.failedToSave?.replace("{error}", String(e)) ?? `Failed to save: ${e}`,
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-md border border-border/80 bg-muted/20 p-4 flex flex-col gap-4">
      <p className="text-xs text-muted-foreground leading-relaxed">
        {mx?.hint ??
          "Enterprise WeChat AI Bot via outbound WebSocket. Credentials are stored locally only."}
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="wecom-bot-id">{fieldLabel("WECOM_BOT_ID", "Bot ID")} *</Label>
          <Input
            id="wecom-bot-id"
            value={botId}
            onChange={(e) => setBotId(e.target.value)}
            placeholder={
              botField?.is_set
                ? botField.redacted_value || placeholderSet
                : (mx?.botIdPlaceholder ?? "WeCom AI Bot ID")
            }
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="wecom-secret">{fieldLabel("WECOM_SECRET", "Secret")} *</Label>
          <Input
            id="wecom-secret"
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={
              secretField?.is_set
                ? secretField.redacted_value || placeholderSet
                : (mx?.secretPlaceholder ?? "Stored encrypted locally")
            }
          />
        </div>
        <div className="grid gap-1.5 sm:col-span-2">
          <Label htmlFor="wecom-ws-url">
            {fieldLabel("WECOM_WEBSOCKET_URL", mx?.websocketUrlLabel ?? "WebSocket URL")}
          </Label>
          <Input
            id="wecom-ws-url"
            value={websocketUrl}
            onChange={(e) => setWebsocketUrl(e.target.value)}
            placeholder={
              wsField?.is_set
                ? wsField.redacted_value || placeholderSet
                : (mx?.websocketUrlPlaceholder ?? "wss://openws.work.weixin.qq.com")
            }
          />
        </div>
        <div className="grid gap-1.5 sm:col-span-2">
          <Label htmlFor="wecom-welcome">{mx?.welcomeLabel ?? "Welcome message"}</Label>
          <textarea
            id="wecom-welcome"
            className="flex min-h-[64px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            rows={2}
            value={welcome}
            onChange={(e) => setWelcome(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
          {mx?.secretHint ?? "Secrets are encrypted locally and never leave this machine."}
        </p>
        <Button
          size="sm"
          onClick={() => void save()}
          disabled={saving}
          prefix={saving ? <Spinner /> : <Save className="h-4 w-4" />}
        >
          {saving ? (t.channels?.saving ?? "Saving…") : (mx?.save ?? "Save configuration")}
        </Button>
      </div>
    </div>
  );
}
