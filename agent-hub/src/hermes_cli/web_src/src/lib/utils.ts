import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Sans stack for layout shells and readable body copy. */
export const themedFont = "font-sans antialiased";

/** Sentence-case body text — avoids Latin display font for CJK UI. */
export const themedBody = "font-sans normal-case antialiased";

/** Section headers and nav labels — medium weight, no forced uppercase. */
export const themedChrome = "font-sans font-medium tracking-normal normal-case antialiased";

/** Sidebar / shell navigation — readable sans for CJK. */
export const hubSidebarLink =
  "font-sans text-sm font-normal normal-case tracking-normal antialiased";

export const hubSidebarSection =
  "font-sans text-xs font-medium normal-case tracking-normal text-text-tertiary antialiased";

export const hubSidebarMeta =
  "font-sans text-sm normal-case tracking-normal leading-snug antialiased";

export const hubPanelTitle =
  "font-sans text-base font-semibold normal-case tracking-normal antialiased";

/** Inline CLI / env snippets — readable mono, not display Courier. */
export const hubInlineCode =
  "font-mono-ui rounded border border-border/50 bg-muted/30 px-1.5 py-0.5 text-[0.8125rem] text-foreground/90 normal-case tracking-normal";

export const GATEWAY_START_CMD = "hermes gateway start";

/** Relative time from a Unix epoch timestamp (seconds). */
export function timeAgo(ts: number): string {
  const delta = Date.now() / 1000 - ts;
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  if (delta < 172800) return "yesterday";
  return `${Math.floor(delta / 86400)}d ago`;
}

/** Relative time from an ISO-8601 timestamp string. */
export function isoTimeAgo(iso: string): string {
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 0 || Number.isNaN(delta)) return "unknown";
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}
