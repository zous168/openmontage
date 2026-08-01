/** Shared Backlot UI preferences — theme & font scale. */

import { el } from "/ui/lib.js";
import { t, themeName } from "/ui/i18n.js";

export const THEME_KEY = "backlot.theme";
export const FONT_SCALE_KEY = "backlot.fontScale";

let currentTheme = localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
let currentFontScale = readStoredFontScale();

function readStoredFontScale() {
  const raw = localStorage.getItem(FONT_SCALE_KEY);
  const n = raw != null ? Number(raw) : 1.12;
  return Number.isFinite(n) ? n : 1.12;
}

export function getTheme() {
  return currentTheme;
}

export function getFontScale() {
  return currentFontScale;
}

export function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = currentTheme;
  localStorage.setItem(THEME_KEY, currentTheme);
}

export function applyFontScale(scale) {
  const n = Number(scale);
  if (!Number.isFinite(n)) return;
  currentFontScale = Math.max(0.85, Math.min(1.4, Math.round(n * 100) / 100));
  document.documentElement.style.setProperty("--fs-scale", String(currentFontScale));
  localStorage.setItem(FONT_SCALE_KEY, String(currentFontScale));
}

export function applyPreferences(prefs = {}) {
  if (prefs.theme) applyTheme(prefs.theme);
  if (prefs.font_scale != null) applyFontScale(prefs.font_scale);
}

export function readLocalPreferences() {
  applyPreferences({
    theme: localStorage.getItem(THEME_KEY) || "dark",
    font_scale: readStoredFontScale(),
  });
}

export function renderThemeToggle(onAfterChange) {
  const next = currentTheme === "light" ? "dark" : "light";
  return el("button", {
    class: "theme-toggle",
    type: "button",
    title: t("switchTheme", { theme: themeName(next) }),
    "aria-label": t("switchTheme", { theme: themeName(next) }),
    "aria-pressed": currentTheme === "light" ? "true" : "false",
    onclick: () => {
      applyTheme(next);
      if (onAfterChange) onAfterChange({ theme: currentTheme });
      else {
        const replacement = renderThemeToggle(onAfterChange);
        document.querySelector(".theme-toggle")?.replaceWith(replacement);
      }
    },
  }, el("span", { class: "theme-toggle-label", "aria-hidden": "true" }, themeName(next).slice(0, 1)));
}
