/** Global settings — preferences, system dependencies, and skill/tool catalog. */

import { brandMark, el, getJSON, patchJSON } from "/ui/lib.js";
import { t } from "/ui/i18n.js";
import { renderLoading } from "/ui/loading.js";
import { renderStylePlaybookField } from "/ui/project-form.js";
import { applyPreferences, getFontScale, getTheme } from "/ui/preferences.js";
import { loadCatalogInto, loadDepsInto, loadDepsManifestInto } from "/ui/system-deps.js";
import { loadEnvConfigInto, saveEnvConfigForm } from "/ui/env-config.js";

function buildModalHeader(title, lead) {
  return el("header", { class: "lib-create-header" },
    el("div", { class: "lib-create-brand" },
      brandMark({ hidden: true }),
      el("div", { class: "lib-create-heading" },
        el("h2", { class: "lib-create-title", id: "libAppSettingsTitle" }, title),
        lead ? el("p", { class: "lib-create-lead" }, lead) : null,
      ),
    ),
  );
}

function mountModal(modalHost, panel, onClose) {
  modalHost.innerHTML = "";
  modalHost.append(
    el("button", {
      class: "modal-close",
      type: "button",
      onclick: onClose,
    }, t("close")),
    panel,
  );
  modalHost.classList.add("open");
  modalHost.setAttribute("aria-hidden", "false");
  modalHost.setAttribute("role", "dialog");
  modalHost.setAttribute("aria-modal", "true");
  document.body.style.overflow = "hidden";
  modalHost.onclick = (e) => {
    if (e.target === modalHost) onClose();
  };
}

function normalizeSettingsTab(tab) {
  if (tab === "deps" || tab === "catalog" || tab === "prefs" || tab === "env") return tab;
  if (tab === "pipelines") return "prefs";
  return "prefs";
}

/**
 * @param {{
 *   modalHost: HTMLElement,
 *   onClose: () => void,
 *   onSaved?: (settings: object) => void | Promise<void>,
 *   initialTab?: "prefs"|"deps"|"catalog"|"env",
 * }} opts
 */
export function openAppSettings({ modalHost, onClose, onSaved, initialTab = "prefs" }) {
  mountModal(modalHost, el("div", { class: "modal-page lib-create-panel app-settings-panel" },
    buildModalHeader(t("globalSettingsTitle"), t("globalSettingsLead")),
    renderLoading(t("loadingSettings"), { block: true }),
  ), onClose);

  return getJSON("/api/settings").then((settings) => {
    const styleField = renderStylePlaybookField(
      settings.style_playbook_options,
      settings.default_style_playbook || "",
    );
    const notesInput = el("textarea", {
      class: "lib-field-input lib-field-textarea",
      name: "default_bootstrap_notes",
      rows: "3",
      maxlength: "2000",
      placeholder: t("globalDefaultNotesHint"),
    }, settings.default_bootstrap_notes || "");

    const themeSelect = el("select", { class: "lib-field-input", name: "theme" },
      el("option", { value: "dark", selected: (settings.theme || getTheme()) === "dark" ? "true" : null }, t("themeDark")),
      el("option", { value: "light", selected: (settings.theme || getTheme()) === "light" ? "true" : null }, t("themeLight")),
    );

    const fontScaleInput = el("input", {
      class: "lib-field-input",
      type: "range",
      name: "font_scale",
      min: "0.85",
      max: "1.4",
      step: "0.01",
      value: String(settings.font_scale ?? getFontScale()),
    });
    const fontScaleLabel = el("span", { class: "lib-field-hint lib-font-scale-value" }, "");
    const syncFontLabel = () => {
      fontScaleLabel.textContent = t("globalFontScaleValue", { value: Number(fontScaleInput.value).toFixed(2) });
    };
    fontScaleInput.addEventListener("input", syncFontLabel);
    syncFontLabel();

    const projectsDir = el("div", { class: "lib-field-readonly lib-field-readonly-path" }, settings.projects_dir || "—");

    const errorBox = el("p", { class: "lib-form-error", hidden: "true" });
    const submitBtn = el("button", {
      class: "lib-form-submit",
      type: "submit",
      form: "appSettingsPrefsForm",
    }, t("saveSettings"));
    const verifyBtn = el("button", { class: "lib-form-submit", type: "button" }, t("depsVerify"));
    const envSaveBtn = el("button", {
      class: "lib-form-submit",
      type: "submit",
      form: "appSettingsEnvForm",
    }, t("saveEnvVars"));

    const prefsForm = el("form", {
      class: "lib-create-form app-settings-pane",
      id: "appSettingsPrefsForm",
      "aria-labelledby": "libAppSettingsTitle",
    },
      el("p", { class: "lib-settings-section-title" }, t("globalDefaultsSection")),
      styleField,
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("globalDefaultNotes")),
        notesInput,
        el("span", { class: "lib-field-hint" }, t("globalDefaultNotesHint")),
      ),
      el("p", { class: "lib-settings-section-title" }, t("globalUiSection")),
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("globalTheme")),
        themeSelect,
      ),
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("globalFontScale")),
        fontScaleInput,
        fontScaleLabel,
        el("span", { class: "lib-field-hint" }, t("globalFontScaleHint")),
      ),
      el("p", { class: "lib-settings-section-title" }, t("globalPathsSection")),
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("globalProjectsDir")),
        projectsDir,
        el("span", { class: "lib-field-hint" }, t("globalProjectsDirHint")),
      ),
    );

    const depsHost = el("div", { class: "deps-host app-settings-pane", hidden: "true" });
    const catalogHost = el("div", { class: "deps-host app-settings-pane", hidden: "true" });
    const envHost = el("div", { class: "deps-host app-settings-pane", hidden: "true" });

    prefsForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.hidden = true;
      submitBtn.disabled = true;
      submitBtn.textContent = t("savingSettings");
      try {
        const body = {
          default_style_playbook: styleField.querySelector("select")?.value || "",
          default_bootstrap_notes: notesInput.value.trim(),
          theme: themeSelect.value,
          font_scale: Number(fontScaleInput.value),
        };
        const updated = await patchJSON("/api/settings", body);
        applyPreferences(updated);
        onClose();
        if (onSaved) await onSaved(updated);
      } catch (err) {
        errorBox.hidden = false;
        errorBox.textContent = err.message || t("settingsFailed");
        submitBtn.disabled = false;
        submitBtn.textContent = t("saveSettings");
      }
    });

    function makeTab(id, label) {
      return el("button", {
        class: "sys-tab",
        type: "button",
        role: "tab",
        "aria-selected": "false",
        onclick: () => switchTab(id),
      }, label);
    }

    const tabPrefs = makeTab("prefs", t("globalPrefsTab"));
    const tabEnv = makeTab("env", t("envTab"));
    const tabDeps = makeTab("deps", t("depsTab"));
    const tabCatalog = makeTab("catalog", t("catalogTab"));
    const tabBar = el("div", { class: "sys-tabs app-settings-tabs", role: "tablist" },
      tabPrefs, tabEnv, tabDeps, tabCatalog);

    let catalogLoaded = false;
    let depsManifestLoaded = false;
    let envLoaded = false;

    async function switchTab(tab) {
      const active = normalizeSettingsTab(tab);
      tabPrefs.classList.toggle("active", active === "prefs");
      tabEnv.classList.toggle("active", active === "env");
      tabDeps.classList.toggle("active", active === "deps");
      tabCatalog.classList.toggle("active", active === "catalog");
      tabPrefs.setAttribute("aria-selected", active === "prefs" ? "true" : "false");
      tabEnv.setAttribute("aria-selected", active === "env" ? "true" : "false");
      tabDeps.setAttribute("aria-selected", active === "deps" ? "true" : "false");
      tabCatalog.setAttribute("aria-selected", active === "catalog" ? "true" : "false");

      prefsForm.hidden = active !== "prefs";
      envHost.hidden = active !== "env";
      depsHost.hidden = active !== "deps";
      catalogHost.hidden = active !== "catalog";
      submitBtn.hidden = active !== "prefs";
      envSaveBtn.hidden = active !== "env";
      verifyBtn.hidden = active !== "deps";

      if (active === "env" && !envLoaded) {
        envLoaded = true;
        await loadEnvConfigInto(envHost, errorBox);
      }
      if (active === "deps" && !depsManifestLoaded) {
        depsManifestLoaded = true;
        await loadDepsManifestInto(depsHost, errorBox);
      }
      if (active === "catalog" && !catalogLoaded) {
        catalogLoaded = true;
        await loadCatalogInto(catalogHost, errorBox);
      }
    }

    envHost.addEventListener("submit", async (ev) => {
      const form = ev.target.closest("#appSettingsEnvForm");
      if (!form) return;
      ev.preventDefault();
      errorBox.hidden = true;
      envSaveBtn.disabled = true;
      envSaveBtn.textContent = t("savingEnvVars");
      try {
        await saveEnvConfigForm(form, errorBox);
        await loadEnvConfigInto(envHost, errorBox);
      } catch (err) {
        errorBox.hidden = false;
        errorBox.textContent = err.message || t("envSaveFailed");
      } finally {
        envSaveBtn.disabled = false;
        envSaveBtn.textContent = t("saveEnvVars");
      }
    });

    verifyBtn.addEventListener("click", async () => {
      verifyBtn.disabled = true;
      verifyBtn.textContent = t("depsVerifying");
      await loadDepsInto(depsHost, errorBox, { verify: false });
      verifyBtn.disabled = false;
      verifyBtn.textContent = t("depsVerify");
    });

    const panel = el("div", { class: "modal-page lib-create-panel app-settings-panel" },
      buildModalHeader(t("globalSettingsTitle"), t("globalSettingsLead")),
      tabBar,
      prefsForm,
      envHost,
      depsHost,
      catalogHost,
      errorBox,
      el("div", { class: "lib-form-actions" },
        el("button", { class: "lib-form-cancel", type: "button", onclick: onClose }, t("cancel")),
        verifyBtn,
        envSaveBtn,
        submitBtn,
      ),
    );

    mountModal(modalHost, panel, onClose);
    switchTab(initialTab);
    if (initialTab === "prefs") themeSelect.focus();
  }).catch((err) => {
    const panel = el("div", { class: "modal-page lib-create-panel" },
      buildModalHeader(t("globalSettingsTitle"), null),
      el("div", { class: "notice warn lib-settings-load-error" },
        el("div", { class: "big" }, t("settingsLoadFailed")),
        el("p", {}, err?.message || t("settingsLoadFailedHint")),
      ),
      el("div", { class: "lib-form-actions" },
        el("button", { class: "lib-form-cancel", type: "button", onclick: onClose }, t("close")),
      ),
    );
    mountModal(modalHost, panel, onClose);
  });
}
