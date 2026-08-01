/** Project settings modal — library cards + board header. */

import { el, getJSON, patchJSON } from "/ui/lib.js";
import { t } from "/ui/i18n.js";
import {
  collectBootstrapInputs,
  renderBootstrapField,
  renderStylePlaybookField,
} from "/ui/project-form.js";
import { renderSourceMediaSection } from "/ui/source-media-preview.js";

const MEDIA_PATH_KEYS = new Set(["source_media_path", "reference_media_path"]);

function buildModalHeader(title, lead) {
  return el("header", { class: "lib-create-header" },
    el("div", { class: "lib-create-brand" },
      el("div", { class: "clapper", "aria-hidden": "true" }),
      el("div", { class: "lib-create-heading" },
        el("h2", { class: "lib-create-title", id: "libModalTitle" }, title),
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

function renderProjectIdField(projectId, createdAt) {
  const hintParts = [t("fieldProjectIdReadonlyHint")];
  if (createdAt) {
    hintParts.push(t("fieldProjectCreatedAt", { date: String(createdAt).slice(0, 10) }));
  }
  return el("label", { class: "lib-field" },
    el("span", { class: "lib-field-label" }, t("fieldProjectId")),
    el("div", { class: "lib-field-readonly" }, projectId),
    el("span", { class: "lib-field-hint" }, hintParts.join(" · ")),
  );
}

/**
 * @param {string} projectId
 * @param {{ modalHost: HTMLElement, onClose: () => void, onSaved?: () => void | Promise<void> }} opts
 */
export function openProjectSettings(projectId, { modalHost, onClose, onSaved }) {
  const pid = projectId;
  const replaceMediaId = `libReplaceMedia-${pid}`;

  return getJSON(`/api/project/${encodeURIComponent(pid)}/settings`).then((settings) => {
    const titleInput = el("input", {
      class: "lib-field-input",
      type: "text",
      name: "title",
      required: "true",
      autocomplete: "off",
      value: settings.title || "",
    });
    const pipelineDisplay = settings.pipeline_type === "unknown"
      ? t("pipelineUnknown")
      : (settings.pipeline_label_zh || settings.pipeline_type);
    const pipelineHint = settings.legacy_marker && settings.pipeline_type === "unknown"
      ? t("fieldPipelineLegacyHint")
      : t("fieldPipelineLocked");
    const pipelineReadonly = el("div", { class: "lib-field-readonly" }, pipelineDisplay);
    const stylePlaybookField = renderStylePlaybookField(
      settings.style_playbook_options,
      settings.style_playbook || "",
    );
    const notesInput = el("textarea", {
      class: "lib-field-input lib-field-textarea",
      name: "notes",
      rows: "3",
      maxlength: "2000",
      placeholder: "可选：给 Agent 的额外说明",
    }, settings.bootstrap_notes || "");

    const bootstrapHost = el("div", { class: "lib-bootstrap-fields" });
    const productionInputs = settings.production_inputs || {};
    const hasLockedMedia = (settings.bootstrap_fields || []).some((f) => f.locked);
    const replaceMediaCheck = el("input", { type: "checkbox", name: "replace_media", id: replaceMediaId });
    const replaceMediaRow = el("label", { class: "lib-field lib-field-checkbox", for: replaceMediaId },
      replaceMediaCheck,
      el("span", {}, t("replaceMedia")),
      el("span", { class: "lib-field-hint" }, t("replaceMediaHint")),
    );
    replaceMediaRow.hidden = !hasLockedMedia;

    function effectiveField(field) {
      if (replaceMediaCheck.checked && field.locked) {
        return { ...field, locked: false, required: false };
      }
      return field;
    }

    function shouldSkipMediaField(field) {
      if (!MEDIA_PATH_KEYS.has(field.key)) return false;
      const src = settings.source_media;
      if (!src?.path) return false;
      const eff = effectiveField(field);
      if (!eff.locked) return false;
      if (field.key === "source_media_path" && src.kind !== "source") return false;
      if (field.key === "reference_media_path" && src.kind !== "reference") return false;
      return true;
    }

    function syncBootstrapFields() {
      bootstrapHost.innerHTML = "";
      const visible = (settings.bootstrap_fields || [])
        .filter((f) => !shouldSkipMediaField(f))
        .map(effectiveField);
      if (visible.length) {
        bootstrapHost.append(
          el("p", { class: "lib-bootstrap-title" }, t("fieldProductionInputs")),
          ...visible.map((f) => renderBootstrapField(f, productionInputs[f.key])),
        );
      }
      if (hasLockedMedia) bootstrapHost.append(replaceMediaRow);
    }
    syncBootstrapFields();

    replaceMediaCheck.addEventListener("change", syncBootstrapFields);

    const errorBox = el("p", { class: "lib-form-error", hidden: "true" });
    const submitBtn = el("button", { class: "lib-form-submit", type: "submit" }, t("saveSettings"));

    const sourcePreview = renderSourceMediaSection(pid, settings.source_media, { compact: true });
    const legacyNotice = settings.legacy_marker
      ? el("p", { class: "lib-settings-legacy-notice" }, t("settingsLegacyNotice"))
      : null;

    const form = el("form", { class: "lib-create-form", "aria-labelledby": "libModalTitle" },
      renderProjectIdField(settings.project_id || pid, settings.created_at),
      legacyNotice,
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldTitle")),
        titleInput,
      ),
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldPipeline")),
        pipelineReadonly,
        el("span", { class: "lib-field-hint" }, pipelineHint),
      ),
      stylePlaybookField,
      sourcePreview,
      bootstrapHost,
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldNotes")),
        notesInput,
      ),
      settings.has_pipeline_state
        ? el("p", { class: "lib-field-hint lib-settings-warning" }, `${t("fieldReadOnly")}：流水线已开始，部分字段已锁定。`)
        : null,
      errorBox,
      el("div", { class: "lib-form-actions" },
        el("button", { class: "lib-form-cancel", type: "button", onclick: onClose }, t("cancel")),
        submitBtn,
      ),
    );

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.hidden = true;
      submitBtn.disabled = true;
      submitBtn.textContent = t("savingSettings");
      try {
        const inputs = collectBootstrapInputs(bootstrapHost);
        await patchJSON(`/api/project/${encodeURIComponent(pid)}/settings`, {
          title: titleInput.value.trim(),
          style_playbook: stylePlaybookField.querySelector("select")?.value || "",
          notes: notesInput.value.trim(),
          inputs: Object.keys(inputs).length ? inputs : null,
          replace_media: Boolean(replaceMediaCheck.checked),
        });
        onClose();
        if (onSaved) await onSaved();
      } catch (err) {
        errorBox.hidden = false;
        errorBox.textContent = err.message || t("settingsFailed");
        submitBtn.disabled = false;
        submitBtn.textContent = t("saveSettings");
      }
    });

    const panel = el("div", { class: "modal-page lib-create-panel" },
      buildModalHeader(t("projectSettingsTitle"), t("projectSettingsLead")),
      form,
    );

    mountModal(modalHost, panel, onClose);
    titleInput.focus();
  }).catch((err) => {
    const panel = el("div", { class: "modal-page lib-create-panel" },
      buildModalHeader(t("projectSettingsTitle"), null),
      renderProjectIdField(pid, null),
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
