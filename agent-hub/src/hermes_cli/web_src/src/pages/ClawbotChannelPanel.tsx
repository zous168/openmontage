import { useCallback, useEffect, useState } from "react";
import * as QRCode from "qrcode";
import { CheckCircle2, QrCode } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api } from "@/lib/api";
import type { ClawbotPlatformExtra, MessagingPlatform } from "@/lib/api";
import {
  CONNECTION_I18N_KEYS,
  resolvePlatformConnectionState,
} from "@/lib/channelConnection";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function ClawbotOnboardingPanel({
  platform,
  onChanged,
  showToast,
}: {
  platform: MessagingPlatform;
  onChanged: () => Promise<void>;
  showToast: (message: string, type: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const mx = t.channels?.clawbot;
  const extra = (platform.platform_extra ?? {}) as ClawbotPlatformExtra;
  const [bound, setBound] = useState(Boolean(extra.bind_status));
  const [sessionReady, setSessionReady] = useState(Boolean(extra.session_ready));
  const [wxid, setWxid] = useState(extra.bound_wxid ?? "");
  const [stats, setStats] = useState(extra.stats ?? { received: 0, replied: 0, today: 0 });
  const [binding, setBinding] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [qrHint, setQrHint] = useState("");

  useEffect(() => {
    const cfg = (platform.platform_extra ?? {}) as ClawbotPlatformExtra;
    setBound(Boolean(cfg.bind_status));
    setSessionReady(Boolean(cfg.session_ready));
    setWxid(cfg.bound_wxid ?? "");
    if (cfg.stats) setStats(cfg.stats);
  }, [platform.platform_extra]);

  const pollBind = useCallback(
    async (token: string) => {
      let activeToken = token;
      for (let i = 0; i < 240; i += 1) {
        const st = await api.getClawbotOnboardingStatus(activeToken);
        if (st.status === "invalid") throw new Error(mx?.bindInvalid ?? "Invalid bind session");
        if (st.status === "expired") throw new Error(mx?.bindTimeout ?? "Scan timed out — try again");
        if (st.refreshed && st.qr_payload) {
          const dataUrl = await QRCode.toDataURL(st.qr_payload, {
            errorCorrectionLevel: "M",
            margin: 1,
            width: 200,
          });
          setQrDataUrl(dataUrl);
          if (st.bind_token) activeToken = st.bind_token;
        }
        if (st.qr_hint) setQrHint(st.qr_hint);
        if (st.status === "confirmed" && st.bound) return st;
        await sleep(500);
      }
      throw new Error(mx?.bindTimeout ?? "Scan timed out — try again");
    },
    [mx?.bindInvalid, mx?.bindTimeout],
  );

  const startBind = async () => {
    setBinding(true);
    setQrHint("");
    setQrDataUrl("");
    try {
      const start = await api.startClawbotOnboarding();
      setQrHint(start.qr_hint ?? mx?.qrHint ?? "Scan with WeChat on your phone");
      const qrContent = start.qr_payload ?? start.bind_token;
      const dataUrl = await QRCode.toDataURL(qrContent, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 200,
      });
      setQrDataUrl(dataUrl);
      await pollBind(start.bind_token);
      setQrDataUrl("");
      showToast(mx?.bindOk ?? "WeChat ClawBot bound successfully", "success");
      await onChanged();
    } catch (e) {
      setQrDataUrl("");
      showToast(String(e), "error");
    } finally {
      setBinding(false);
    }
  };

  const conn = resolvePlatformConnectionState(platform);
  const connKey = conn ? CONNECTION_I18N_KEYS[conn] : null;
  const connLabel = connKey
    ? ((t.channels as Record<string, string> | undefined)?.[connKey] ?? conn)
    : null;

  return (
    <div className="rounded-md border border-border/80 bg-muted/20 p-4 flex flex-col gap-3">
      <p className="text-xs text-muted-foreground leading-relaxed">
        {mx?.hint ??
          "Gateway platform (gateways.clawbot). Scan QR to bind WeChat; AI replies reuse the system LLM."}
      </p>
      {bound ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
            <span>{mx?.boundLabel ?? "Bound"}</span>
            {wxid && <code className="text-xs text-muted-foreground">{wxid}</code>}
            <span className="text-xs text-muted-foreground">
              {mx?.stats
                ?.replace("{received}", String(stats.received))
                .replace("{replied}", String(stats.replied))
                .replace("{today}", String(stats.today)) ??
                `Received ${stats.received} · Replied ${stats.replied} · Today ${stats.today}`}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">{mx?.sessionLabel ?? "Session"}</span>
            <Badge tone={sessionReady ? "success" : "warning"}>
              {sessionReady
                ? (mx?.sessionReady ?? "Ready")
                : (mx?.sessionPending ?? "Await first message")}
            </Badge>
            {platform.enabled && connLabel ? (
              <>
                <span className="text-muted-foreground">{mx?.gatewayLabel ?? "Gateway"}</span>
                <Badge
                  tone={
                    conn === "connected"
                      ? "success"
                      : conn === "error"
                        ? "destructive"
                        : "warning"
                  }
                >
                  {connLabel}
                </Badge>
              </>
            ) : null}
          </div>
          {bound && !sessionReady ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {mx?.sessionHint ??
                "Send any message to ClawBot in WeChat first to establish a session."}
            </p>
          ) : null}
          {!platform.enabled ? (
            <p className="text-xs text-muted-foreground">
              {mx?.enableSwitchHint ?? "Turn on the switch above to connect Gateway."}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{mx?.unbound ?? "Not bound yet."}</p>
      )}
      {qrDataUrl && (
        <div className="flex flex-col items-start gap-2">
          <img
            src={qrDataUrl}
            alt={mx?.qrAlt ?? "ClawBot bind QR code"}
            className={cn("rounded border border-border bg-white p-2")}
          />
          {qrHint && <span className="text-xs text-muted-foreground">{qrHint}</span>}
        </div>
      )}
      <div>
        <Button
          size="sm"
          onClick={() => void startBind()}
          disabled={binding}
          prefix={binding ? <Spinner /> : <QrCode className="h-4 w-4" />}
        >
          {binding
            ? (mx?.binding ?? "Waiting for scan…")
            : bound
              ? (mx?.rebind ?? "Re-bind WeChat")
              : (mx?.bind ?? "Scan QR to bind")}
        </Button>
      </div>
    </div>
  );
}
