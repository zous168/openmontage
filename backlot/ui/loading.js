/** Unified loading indicator for Backlot UI. */

import { el } from "/ui/lib.js";
import { t } from "/ui/i18n.js";

/**
 * @param {string} [message]
 * @param {{ compact?: boolean, block?: boolean, className?: string }} [opts]
 */
export function renderLoading(message, { compact = false, block = true, className = "" } = {}) {
  const label = message || t("loading");
  const classes = [
    "bl-loading",
    compact ? "bl-loading-compact" : "",
    block ? "bl-loading-block" : "",
    className,
  ].filter(Boolean).join(" ");
  return el("div", {
    class: classes,
    role: "status",
    "aria-live": "polite",
    "aria-busy": "true",
  },
    el("span", { class: "bl-loading-spinner", "aria-hidden": "true" }),
    el("span", { class: "bl-loading-label" }, label),
  );
}

/** Replace host contents with a centered loading state. */
export function showLoading(host, message) {
  host.innerHTML = "";
  host.append(renderLoading(message));
}
