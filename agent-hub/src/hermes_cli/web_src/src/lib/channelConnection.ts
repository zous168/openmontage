import type { MessagingPlatform } from "@/lib/api";

export const CONNECTION_STATES = [
  "connected",
  "connecting",
  "disconnected",
  "gateway_stopped",
  "error",
  "paused",
] as const;

export type ConnectionState = (typeof CONNECTION_STATES)[number];

export function resolvePlatformConnectionState(
  platform: Pick<
    MessagingPlatform,
    "enabled" | "configured" | "gateway_running" | "connection_state" | "error_message"
  >,
): ConnectionState | null {
  if (!platform.enabled || !platform.configured) return null;
  const raw = platform.connection_state;
  if (raw && (CONNECTION_STATES as readonly string[]).includes(raw)) {
    return raw as ConnectionState;
  }
  // Hub not restarted yet — infer from fields we always have.
  if (!platform.gateway_running) return "gateway_stopped";
  if (platform.error_message) return "error";
  return "connecting";
}

export const CONNECTION_I18N_KEYS: Record<ConnectionState, string> = {
  connected: "connConnected",
  connecting: "connConnecting",
  disconnected: "connDisconnected",
  gateway_stopped: "connGatewayStopped",
  error: "connError",
  paused: "connPaused",
};
