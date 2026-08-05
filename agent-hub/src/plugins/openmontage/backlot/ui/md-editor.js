/** Split Markdown editor — toolbar, edit / preview / split modes. */

import { el } from "/ui/lib.js";
import { t } from "/ui/i18n.js";
import { renderMarkdown } from "/ui/md-render.js";

/**
 * @param {{
 *   value?: string,
 *   placeholder?: string,
 *   onChange?: () => void,
 * }} opts
 */
export function createMdEditor({ value = "", placeholder = "", onChange } = {}) {
  let mode = "split";

  const textarea = el("textarea", {
    class: "md-editor-textarea",
    spellcheck: "false",
    placeholder,
  }, value);

  const preview = el("div", { class: "md-editor-preview prose" });
  const editPane = el("div", { class: "md-editor-pane md-editor-pane-edit" }, textarea);
  const previewPane = el("div", { class: "md-editor-pane md-editor-pane-preview" }, preview);
  const body = el("div", { class: "md-editor-body md-editor-mode-split" }, editPane, previewPane);

  function updatePreview() {
    preview.innerHTML = renderMarkdown(textarea.value);
  }

  function setMode(next) {
    mode = next;
    body.className = `md-editor-body md-editor-mode-${mode}`;
    for (const btn of modeBar.querySelectorAll("[data-mode]")) {
      btn.classList.toggle("active", btn.dataset.mode === mode);
      btn.setAttribute("aria-selected", btn.dataset.mode === mode ? "true" : "false");
    }
    if (mode !== "edit") updatePreview();
  }

  function wrapSelection(before, after = before) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    const selected = text.slice(start, end) || t("mdEditorSelection");
    const next = text.slice(0, start) + before + selected + after + text.slice(end);
    textarea.value = next;
    const cursor = start + before.length + selected.length + after.length;
    textarea.setSelectionRange(cursor, cursor);
    textarea.focus();
    emitChange();
    updatePreview();
  }

  function insertLine(prefix) {
    const start = textarea.selectionStart;
    const text = textarea.value;
    const lineStart = text.lastIndexOf("\n", start - 1) + 1;
    const next = text.slice(0, lineStart) + prefix + text.slice(lineStart);
    textarea.value = next;
    textarea.setSelectionRange(start + prefix.length, start + prefix.length);
    textarea.focus();
    emitChange();
    updatePreview();
  }

  function emitChange() {
    updatePreview();
    if (onChange) onChange();
  }

  textarea.addEventListener("input", emitChange);
  textarea.addEventListener("keydown", (ev) => {
    if (ev.key === "Tab") {
      ev.preventDefault();
      wrapSelection("  ", "");
      return;
    }
    if (ev.ctrlKey || ev.metaKey) {
      if (ev.key === "b") {
        ev.preventDefault();
        wrapSelection("**", "**");
      } else if (ev.key === "i") {
        ev.preventDefault();
        wrapSelection("*", "*");
      }
    }
  });

  const toolbar = el("div", { class: "md-editor-toolbar", role: "toolbar" });
  const tools = [
    { label: "H1", title: t("mdToolH1"), action: () => insertLine("# ") },
    { label: "H2", title: t("mdToolH2"), action: () => insertLine("## ") },
    { label: "H3", title: t("mdToolH3"), action: () => insertLine("### ") },
    { label: "B", title: t("mdToolBold"), action: () => wrapSelection("**", "**") },
    { label: "I", title: t("mdToolItalic"), action: () => wrapSelection("*", "*") },
    { label: "`", title: t("mdToolCode"), action: () => wrapSelection("`", "`") },
    { label: "•", title: t("mdToolList"), action: () => insertLine("- ") },
    { label: "1.", title: t("mdToolOrdered"), action: () => insertLine("1. ") },
    { label: "[]", title: t("mdToolLink"), action: () => wrapSelection("[", "](url)") },
    { label: "```", title: t("mdToolFence"), action: () => wrapSelection("```\n", "\n```") },
  ];
  for (const tool of tools) {
    toolbar.append(el("button", {
      class: "md-editor-tool",
      type: "button",
      title: tool.title,
      onclick: tool.action,
    }, tool.label));
  }

  const modeBar = el("div", { class: "md-editor-modes", role: "tablist" });
  for (const item of [
    { id: "edit", label: t("mdModeEdit") },
    { id: "split", label: t("mdModeSplit") },
    { id: "preview", label: t("mdModePreview") },
  ]) {
    modeBar.append(el("button", {
      class: `md-editor-mode${item.id === mode ? " active" : ""}`,
      type: "button",
      role: "tab",
      "data-mode": item.id,
      "aria-selected": item.id === mode ? "true" : "false",
      onclick: () => setMode(item.id),
    }, item.label));
  }

  const host = el("div", { class: "md-editor" }, modeBar, toolbar, body);
  updatePreview();

  return {
    host,
    getValue: () => textarea.value,
    setValue: (text) => {
      textarea.value = text ?? "";
      emitChange();
    },
    focus: () => textarea.focus(),
  };
}
