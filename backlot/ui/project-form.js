/** Shared bootstrap form fields for create / settings modals. */

import { el, postForm } from "/ui/lib.js";
import { t } from "/ui/i18n.js";

/** Pull the first http(s) URL out of Douyin/Short share paste text. */
export function extractMediaUrl(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const match = text.match(/https?:\/\/[^\s<>"'，。；、）\]】]+/i);
  return match ? match[0].replace(/[.,;\)\]}」]+$/, "") : text;
}

export function renderPathField(field, initialValue) {
  const key = field.key;
  const isReference = key === "reference_media_path";
  const pathInput = el("input", {
    class: "lib-field-input lib-field-path",
    type: "text",
    name: key,
    "data-key": key,
    required: field.required ? "true" : null,
    autocomplete: "off",
    spellcheck: "false",
    placeholder: t("fieldPathPlaceholder"),
    value: initialValue != null && initialValue !== "" ? String(initialValue) : null,
  });
  const fileInput = el("input", {
    type: "file",
    class: "lib-field-file-input",
    accept: isReference ? "video/*,.mp4,.mov,.webm,.mkv,.m4v" : "video/*,audio/*,.mp4,.mov,.webm,.mkv,.mp3,.wav,.m4a,.aac,.ogg,.flac",
    hidden: "true",
  });
  const status = el("span", { class: "lib-field-file-status", "aria-live": "polite" });
  const pickBtn = el("button", {
    type: "button",
    class: "lib-field-file-btn",
    onclick: () => fileInput.click(),
  }, t("browseFile"));

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    pickBtn.disabled = true;
    status.textContent = t("uploading");
    status.classList.remove("is-error");
    try {
      const fd = new FormData();
      fd.append("file", file, file.name);
      const data = await postForm("/api/stage-media", fd);
      pathInput.value = data.path;
      status.textContent = t("fileSelected", { name: file.name });
    } catch (err) {
      status.textContent = err.message || t("uploadFailed");
      status.classList.add("is-error");
    } finally {
      pickBtn.disabled = false;
      fileInput.value = "";
    }
  });

  return el("div", { class: "lib-field-file" },
    el("div", { class: "lib-field-file-row" }, pickBtn, status),
    pathInput,
  );
}

export function renderBootstrapField(field, initialValue) {
  const key = field.key;
  if (Array.isArray(initialValue)) initialValue = initialValue.join(", ");
  const label = el("span", { class: "lib-field-label" }, field.label_zh + (field.required ? " *" : ""));
  let control;
  if (field.locked) {
    const current = field.current_value || initialValue || "—";
    control = el("div", { class: "lib-field-readonly", "data-key": key }, current);
  } else if (field.type === "select" && Array.isArray(field.options)) {
    control = el("select", { class: "lib-field-input", name: key, "data-key": key, required: field.required ? "true" : null },
      el("option", { value: "" }, t("selectOption")),
      ...field.options.map((o) => el("option", { value: o.value }, o.label_zh)),
    );
  } else if (field.type === "number") {
    control = el("input", {
      class: "lib-field-input",
      type: "number",
      name: key,
      "data-key": key,
      min: field.min != null ? String(field.min) : null,
      max: field.max != null ? String(field.max) : null,
      placeholder: field.hint_zh || "",
    });
  } else if (field.type === "text") {
    control = el("textarea", {
      class: "lib-field-input lib-field-textarea",
      name: key,
      "data-key": key,
      rows: "3",
      required: field.required ? "true" : null,
      placeholder: field.hint_zh || "",
    });
  } else if (field.type === "url") {
    control = el("input", {
      class: "lib-field-input",
      type: "text",
      inputmode: "url",
      name: key,
      "data-key": key,
      "data-field-type": "url",
      required: field.required ? "true" : null,
      autocomplete: "off",
      placeholder: field.hint_zh || "https://",
    });
    control.addEventListener("blur", () => {
      const cleaned = extractMediaUrl(control.value);
      if (cleaned) control.value = cleaned;
    });
  } else if (field.type === "path") {
    control = renderPathField(field, initialValue);
  } else {
    control = el("input", {
      class: "lib-field-input",
      type: "text",
      name: key,
      "data-key": key,
      required: field.required ? "true" : null,
      autocomplete: "off",
      placeholder: field.hint_zh || "",
    });
  }
  if (!field.locked && initialValue != null && initialValue !== "" && control?.value !== undefined) {
    control.value = String(initialValue);
  } else if (!field.locked && initialValue != null && initialValue !== "" && control?.tagName === "TEXTAREA") {
    control.value = String(initialValue);
  } else if (!field.locked && initialValue != null && initialValue !== "" && field.type === "select" && control?.tagName === "SELECT") {
    control.value = String(initialValue);
  }
  return el("label", { class: "lib-field lib-bootstrap-field", "data-field-key": key },
    label,
    control,
    field.hint_zh && field.type !== "text" && field.type !== "number"
      ? el("span", { class: "lib-field-hint" }, field.hint_zh)
      : null,
  );
}

export function collectBootstrapInputs(container) {
  const inputs = {};
  for (const node of container.querySelectorAll("[data-key]")) {
    if (node.classList?.contains("lib-field-readonly")) continue;
    const key = node.dataset.key;
    let val = node.value != null ? String(node.value).trim() : "";
    if (node.dataset.fieldType === "url" || key.endsWith("_url")) {
      val = extractMediaUrl(val);
    }
    if (val) inputs[key] = node.type === "number" ? Number(val) : val;
  }
  return inputs;
}

export function renderStylePlaybookField(options, selectedValue = "") {
  const hint = el("p", { class: "lib-field-hint lib-style-playbook-hint" }, "");
  const select = el("select", { class: "lib-field-input", name: "style_playbook" },
    ...(options || [{ value: "", label_zh: t("stylePlaybookDefault") }]).map((o) => {
      const label = o.label_zh || o.value;
      const title = o.hint_zh ? `${label} — ${o.hint_zh}` : label;
      return el("option", {
        value: o.value,
        title,
        selected: o.value === (selectedValue || "") ? "true" : null,
      }, label);
    }),
  );
  function syncHint() {
    const picked = (options || []).find((o) => o.value === select.value);
    hint.textContent = picked?.hint_zh || t("fieldStylePlaybookHint");
  }
  select.addEventListener("change", syncHint);
  syncHint();
  return el("label", { class: "lib-field" },
    el("span", { class: "lib-field-label" }, t("fieldStylePlaybook")),
    select,
    hint,
  );
}
