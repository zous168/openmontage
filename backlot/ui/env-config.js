/** Environment variables tab — edit repo ``.env`` from global settings. */

import { el, getJSON, patchJSON } from "/ui/lib.js";
import { t } from "/ui/i18n.js";

function renderSummary(data) {
  return el("div", { class: "deps-summary env-summary" },
    el("div", { class: "deps-summary-item" },
      el("span", { class: "deps-summary-num" }, `${data.configured_count ?? 0}/${data.total_count ?? 0}`),
      el("span", { class: "deps-summary-label" }, t("envConfiguredCount")),
    ),
    el("div", { class: "deps-summary-item env-path-item" },
      el("span", { class: "deps-summary-label" }, t("envFilePath")),
      el("code", { class: "env-file-path" }, data.env_path || "—"),
    ),
  );
}

function renderEnvField(item) {
  const input = el("input", {
    class: "lib-field-input env-field-input",
    type: "password",
    name: item.name,
    autocomplete: "off",
    spellcheck: "false",
    placeholder: item.configured ? t("envKeepConfigured", { masked: item.masked_value }) : t("envEnterValue"),
    "data-configured": item.configured ? "true" : "false",
  });
  const clearBtn = item.configured
    ? el("button", {
      class: "env-clear-btn",
      type: "button",
      title: t("envClearValue"),
      onclick: () => {
        input.value = "";
        input.dataset.clear = "true";
        input.placeholder = t("envClearPending");
      },
    }, t("envClear"))
    : null;

  return el("label", { class: "env-field" },
    el("div", { class: "env-field-head" },
      el("span", { class: "env-field-name" }, item.name),
      item.configured
        ? el("span", { class: "deps-badge deps-badge-ok" }, t("envConfigured"))
        : el("span", { class: "deps-badge deps-badge-pending" }, t("envNotConfigured")),
    ),
    item.purpose
      ? el("p", { class: "env-field-purpose" }, item.purpose)
      : null,
    item.hint
      ? el("p", { class: "env-field-hint" }, item.hint)
      : null,
    el("div", { class: "env-field-row" }, input, clearBtn),
    el("span", { class: "lib-field-hint env-field-path" }, item.path || t("envVarPath", { name: `$${item.name}` })),
  );
}

export function renderEnvConfig(data, { formId = "appSettingsEnvForm" } = {}) {
  const sectionsHost = el("div", { class: "env-sections" });
  for (const section of data.sections || []) {
    const body = el("div", { class: "env-section-body" },
      ...(section.items || []).map(renderEnvField),
    );
    sectionsHost.append(el("details", { class: "env-section", open: "open" },
      el("summary", { class: "env-section-summary" },
        el("span", { class: "env-section-title" }, section.label || section.id),
        el("span", { class: "catalog-count" }, String((section.items || []).length)),
      ),
      section.description
        ? el("p", { class: "env-section-desc" }, section.description)
        : null,
      body,
    ));
  }

  return el("div", { class: "env-config-report" },
    renderSummary(data),
    el("p", { class: "lib-field-hint env-config-lead" }, t("envConfigLead")),
    el("form", {
      class: "lib-create-form app-settings-pane env-config-form",
      id: formId,
    }, sectionsHost),
  );
}

export async function loadEnvConfigInto(host, errorBox, { formId = "appSettingsEnvForm", onRendered } = {}) {
  errorBox.hidden = true;
  host.innerHTML = "";
  host.append(el("p", { class: "deps-loading" }, t("envLoading")));
  try {
    const data = await getJSON("/api/system/env-vars");
    host.innerHTML = "";
    host.append(renderEnvConfig(data, { formId }));
    if (onRendered) onRendered(data);
  } catch (err) {
    errorBox.hidden = false;
    errorBox.textContent = err.message || t("envLoadFailed");
    host.innerHTML = "";
  }
}

export async function saveEnvConfigForm(form, errorBox) {
  if (!form) return null;
  errorBox.hidden = true;
  const values = {};
  for (const input of form.querySelectorAll("input[name]")) {
    const name = input.name;
    const typed = input.value.trim();
    if (typed) {
      values[name] = typed;
      continue;
    }
    if (input.dataset.clear === "true") {
      values[name] = "";
    }
  }
  if (!Object.keys(values).length) {
    errorBox.hidden = false;
    errorBox.textContent = t("envNothingToSave");
    return null;
  }
  return patchJSON("/api/system/env-vars", { values });
}
