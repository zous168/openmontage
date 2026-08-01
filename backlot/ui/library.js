import { brandMark, deleteJSON, el, fmtAgo, getJSON, patchJSON, postJSON, subscribe, thumbURL } from "/ui/lib.js";
import { artifactLabel, stageLabel, statusLabel, t } from "/ui/i18n.js";
import { renderLoading } from "/ui/loading.js";
import {
  renderBootstrapField,
  renderStylePlaybookField,
  collectBootstrapInputs,
} from "/ui/project-form.js";
import { openProjectSettings } from "/ui/project-settings.js";
import { openAppSettings } from "/ui/app-settings.js";
import { applyPreferences, readLocalPreferences, renderThemeToggle } from "/ui/preferences.js";

const grid = document.getElementById("grid");
const modalHost = document.getElementById("createModal");
let pipelinesCache = null;
let stylePlaybooksCache = null;
let appSettingsCache = null;
let firstPaint = true;

readLocalPreferences();

function closeModal() {
  modalHost.classList.remove("open");
  modalHost.setAttribute("aria-hidden", "true");
  modalHost.removeAttribute("role");
  modalHost.innerHTML = "";
  document.body.style.overflow = "";
}

function openModal(panel, { onBackdropClick = closeModal } = {}) {
  modalHost.innerHTML = "";
  modalHost.append(
    el("button", {
      class: "modal-close",
      type: "button",
      onclick: closeModal,
    }, t("close")),
    panel,
  );
  modalHost.classList.add("open");
  modalHost.setAttribute("aria-hidden", "false");
  modalHost.setAttribute("role", "dialog");
  modalHost.setAttribute("aria-modal", "true");
  document.body.style.overflow = "hidden";
  modalHost.onclick = (e) => {
    if (e.target === modalHost) onBackdropClick();
  };
}

function renderGlobalSettingsButton() {
  return el("button", {
    class: "global-settings-btn",
    type: "button",
    onclick: () => openAppSettingsModal(),
  }, t("globalSettings"));
}

function openAppSettingsModal(initialTab = "prefs") {
  const params = new URLSearchParams(location.search);
  const tab = normalizeAppSettingsTab(params.get("tab") || initialTab);
  return openAppSettings({
    modalHost,
    onClose: closeModal,
    initialTab: tab,
    onSaved: (settings) => {
      appSettingsCache = settings;
      refreshToolbar();
    },
  });
}

function normalizeAppSettingsTab(tab) {
  if (tab === "deps" || tab === "catalog" || tab === "prefs" || tab === "env") return tab;
  if (tab === "pipelines") return "prefs";
  return "prefs";
}

function refreshToolbar() {
  const toolbar = document.getElementById("libToolbar");
  toolbar.innerHTML = "";
  toolbar.append(
    renderCreateButton(),
    renderPipelinesButton(),
    renderGlobalSettingsButton(),
    renderThemeToggle(refreshThemeToggle),
  );
}

function renderPipelinesButton() {
  return el("a", {
    class: "global-settings-btn",
    href: "/pipelines",
  }, t("pipeConfigNav"));
}

function refreshThemeToggle() {
  document.querySelector(".theme-toggle")?.replaceWith(renderThemeToggle(refreshThemeToggle));
}

function renderCreateButton() {
  return el("button", {
    class: "create-project-btn",
    type: "button",
    onclick: () => openCreateModal().catch(console.error),
  }, t("createProject"));
}

refreshToolbar();

async function loadAppSettings() {
  try {
    appSettingsCache = await getJSON("/api/settings");
    applyPreferences(appSettingsCache);
    refreshToolbar();
  } catch {
    appSettingsCache = null;
  }
}

void loadAppSettings();

function slugifyTitle(title) {
  return String(title || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-+/g, "-")
    .slice(0, 64);
}

async function loadPipelines() {
  if (pipelinesCache) return pipelinesCache;
  pipelinesCache = await getJSON("/api/pipelines");
  return pipelinesCache;
}

async function loadStylePlaybooks() {
  if (stylePlaybooksCache) return stylePlaybooksCache;
  stylePlaybooksCache = await getJSON("/api/style-playbooks");
  return stylePlaybooksCache;
}

function openSettingsModal(project) {
  return openProjectSettings(project.project_id, {
    modalHost: modalHost,
    onClose: closeModal,
    onSaved: render,
  });
}

function closeCreateModal() {
  closeModal();
}

function buildModalHeader(title, lead) {
  return el("header", { class: "lib-create-header" },
    el("div", { class: "lib-create-brand" },
      brandMark({ hidden: true }),
      el("div", { class: "lib-create-heading" },
        el("h2", { class: "lib-create-title", id: "libModalTitle" }, title),
        lead ? el("p", { class: "lib-create-lead" }, lead) : null,
      ),
    ),
  );
}

function openDeleteModal(project) {
  const title = project.title || project.project_id;
  const errorBox = el("p", { class: "lib-form-error", hidden: "true" });
  const confirmBtn = el("button", {
    class: "lib-form-submit lib-form-danger",
    type: "button",
  }, t("deleteProject"));

  confirmBtn.addEventListener("click", async () => {
    errorBox.hidden = true;
    confirmBtn.disabled = true;
    confirmBtn.textContent = t("deleting");
    try {
      await deleteJSON(`/api/projects/${encodeURIComponent(project.project_id)}`);
      closeModal();
      await render();
    } catch (err) {
      errorBox.hidden = false;
      errorBox.textContent = err.message || t("deleteFailed");
      confirmBtn.disabled = false;
      confirmBtn.textContent = t("deleteProject");
    }
  });

  const panel = el("div", { class: "modal-page lib-create-panel" },
    buildModalHeader(t("deleteProjectTitle"), t("deleteProjectHint")),
    el("div", { class: "lib-create-body" },
      el("p", { class: "lib-delete-target" }, t("deleteProjectConfirm", { title })),
      errorBox,
      el("div", { class: "lib-form-actions" },
        el("button", { class: "lib-form-cancel", type: "button", onclick: closeModal }, t("cancel")),
        confirmBtn,
      ),
    ),
  );
  openModal(panel);
  confirmBtn.focus();
}

function openCreateModal() {
  return Promise.all([loadPipelines(), loadStylePlaybooks()]).then(([pipelines, stylePlaybooks]) => {
    const idInput = el("input", {
      class: "lib-field-input",
      type: "text",
      name: "project_id",
      required: "true",
      autocomplete: "off",
      spellcheck: "false",
      placeholder: "my-promo-video",
    });
    const titleInput = el("input", {
      class: "lib-field-input",
      type: "text",
      name: "title",
      required: "true",
      autocomplete: "off",
      placeholder: "春季新品带货口播",
    });
    titleInput.addEventListener("input", () => {
      if (!idInput.dataset.touched) {
        idInput.value = slugifyTitle(titleInput.value);
      }
    });
    idInput.addEventListener("input", () => {
      idInput.dataset.touched = "1";
    });

    const pipelineSelect = el("select", { class: "lib-field-input", name: "pipeline_type", required: "true" },
      el("option", { value: "" }, t("selectPipeline")),
      ...pipelines.map((p) => el("option", {
        value: p.id,
        title: p.summary_zh || p.description || "",
      }, p.label_zh)),
    );
    const pipelineHint = el("p", { class: "lib-field-hint lib-pipeline-hint" }, "");
    const bootstrapHost = el("div", { class: "lib-bootstrap-fields" });

    function syncBootstrapFields() {
      const picked = pipelines.find((p) => p.id === pipelineSelect.value);
      pipelineHint.textContent = picked
        ? (picked.summary_zh || picked.description || "")
        : "";
      bootstrapHost.innerHTML = "";
      if (picked?.bootstrap_fields?.length) {
        bootstrapHost.append(
          el("p", { class: "lib-bootstrap-title" }, t("fieldProductionInputs")),
          ...picked.bootstrap_fields.map((f) => renderBootstrapField(f)),
        );
      }
    }

    pipelineSelect.addEventListener("change", syncBootstrapFields);

    const stylePlaybookField = renderStylePlaybookField(
      stylePlaybooks,
      appSettingsCache?.default_style_playbook || "",
    );

    const notesInput = el("textarea", {
      class: "lib-field-input lib-field-textarea",
      name: "notes",
      rows: "3",
      maxlength: "2000",
      placeholder: "可选：给 Agent 的额外说明",
    }, appSettingsCache?.default_bootstrap_notes || "");

    const errorBox = el("p", { class: "lib-form-error", hidden: "true" });
    const submitBtn = el("button", { class: "lib-form-submit", type: "submit" }, t("submitCreate"));

    const form = el("form", { class: "lib-create-form", "aria-labelledby": "libModalTitle" },
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldProjectId")),
        idInput,
        el("span", { class: "lib-field-hint" }, t("fieldProjectIdHint")),
      ),
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldTitle")),
        titleInput,
      ),
      el("label", { class: "lib-field lib-field-emphasis" },
        el("span", { class: "lib-field-label" }, t("fieldPipeline")),
        pipelineSelect,
        pipelineHint,
      ),
      stylePlaybookField,
      bootstrapHost,
      el("label", { class: "lib-field" },
        el("span", { class: "lib-field-label" }, t("fieldNotes")),
        notesInput,
      ),
      errorBox,
      el("div", { class: "lib-form-actions" },
        el("button", { class: "lib-form-cancel", type: "button", onclick: closeCreateModal }, t("cancel")),
        submitBtn,
      ),
    );

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      errorBox.hidden = true;
      submitBtn.disabled = true;
      submitBtn.textContent = t("creating");
      try {
        const inputs = collectBootstrapInputs(bootstrapHost);
        const body = {
          project_id: idInput.value.trim(),
          title: titleInput.value.trim(),
          pipeline_type: pipelineSelect.value,
          style_playbook: stylePlaybookField.querySelector("select")?.value || null,
          notes: notesInput.value.trim() || null,
          inputs: Object.keys(inputs).length ? inputs : null,
        };
        const result = await postJSON("/api/projects", body);
        const staticSuffix = new URLSearchParams(location.search).has("static") ? "?static=1" : "";
        location.href = `/p/${encodeURIComponent(result.project_id)}${staticSuffix}`;
      } catch (err) {
        errorBox.hidden = false;
        errorBox.textContent = err.message || t("createFailed");
        submitBtn.disabled = false;
        submitBtn.textContent = t("submitCreate");
      }
    });

    const panel = el("div", { class: "modal-page lib-create-panel" },
      buildModalHeader(t("createProjectTitle"), t("createProjectLead")),
      el("details", { class: "lib-create-more" },
        el("summary", {}, t("createProjectMore")),
        el("p", {}, t("createProjectHint")),
      ),
      form,
    );

    openModal(panel);
    titleInput.focus();
  });
}

function miniRail(states) {
  const rail = el("div", { class: "mini-rail" });
  for (const s of states) {
    const cls = s.status === "completed" ? "d"
      : s.status === "in_progress" ? "a"
      : s.status === "awaiting_human" ? "w" : "";
    rail.append(el("i", { class: cls, title: `${stageLabel(s.name)}: ${statusLabel(s.status)}` }));
  }
  return rail;
}

function card(p) {
  const poster = el("div", { class: "lib-poster" });
  if (p.poster) {
    poster.append(el("img", { src: thumbURL(p.project_id, p.poster, 640), loading: "lazy", alt: "" }));
  } else {
    poster.append(el("span", { class: "lp-txt" }, t("noMediaYet")));
  }
  if (p.live && p.active_stage) {
    poster.append(el("span", { class: "lp-live" },
      el("span", { class: "dot" }),
      p.awaiting_human ? t("awaitingYou") : `${t("live")} · ${stageLabel(p.active_stage).toUpperCase()}`));
  } else if (p.awaiting_human) {
    poster.append(el("span", { class: "lp-live" }, t("awaitingYou")));
  }

  const meta = el("div", { class: "lb-meta" },
    el("span", {
      class: `chip${p.has_reference ? " chip-ref" : ""}`,
    }, p.pipeline_label_zh || p.pipeline_type || t("unknown")),
    p.scene_count ? el("span", { class: "chip" }, t("scenes", { n: p.scene_count })) : null,
    p.render_count ? el("span", { class: "chip" }, t("renders", { n: p.render_count })) : null,
    el("span", { class: "when" }, fmtAgo(p.last_activity)),
  );

  const staticSuffix = new URLSearchParams(location.search).has("static") ? "?static=1" : "";
  const link = el("a", {
    class: `lib-card${p.live ? " live-card" : ""}`,
    href: `/p/${p.project_id}${staticSuffix}`,
    style: "text-decoration:none;color:inherit",
  },
    poster,
    el("div", { class: "lib-body" },
      el("h3", {}, p.title || p.project_id),
      meta,
      p.stage_states.length ? miniRail(p.stage_states) : null,
    ),
  );

  const settingsBtn = el("button", {
    class: "lib-card-footer-btn",
    type: "button",
    onclick: (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openSettingsModal(p).catch(console.error);
    },
  }, t("projectSettings"));

  const deleteBtn = el("button", {
    class: "lib-card-footer-btn lib-card-footer-danger",
    type: "button",
    onclick: (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openDeleteModal(p);
    },
  }, t("deleteProject"));

  const footer = el("div", { class: "lib-card-footer" }, settingsBtn, deleteBtn);

  return el("div", { class: "lib-card-wrap" },
    link,
    footer,
  );
}

async function render() {
  const showInitialLoading = firstPaint;
  document.body.classList.toggle("first", firstPaint);
  firstPaint = false;

  if (showInitialLoading) {
    grid.innerHTML = "";
    grid.append(renderLoading(t("loadingProjects"), { block: true }));
  }

  const projects = await getJSON("/api/projects");
  document.getElementById("count").textContent = t("projects", { n: projects.length });
  const liveCount = projects.filter((p) => p.live).length;
  const badge = document.getElementById("liveBadge");
  badge.classList.toggle("idle", liveCount === 0);
  document.getElementById("liveText").textContent = liveCount ? t("liveCount", { n: liveCount }) : t("idle");
  grid.innerHTML = "";
  const empty = document.getElementById("empty");
  empty.hidden = projects.length > 0;
  if (!projects.length) {
    empty.innerHTML = "";
    empty.append(
      el("p", {}, t("noProjectsLead")),
      el("button", {
        class: "create-project-btn lib-empty-create",
        type: "button",
        onclick: () => openCreateModal().catch(console.error),
      }, t("createProject")),
    );
  }
  for (const p of projects) grid.append(card(p));
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && modalHost.classList.contains("open")) closeModal();
});

render().catch(console.error);
const urlParams = new URLSearchParams(location.search);
if (urlParams.get("app-settings")) {
  openAppSettingsModal(normalizeAppSettingsTab(urlParams.get("tab"))).catch(console.error);
}
const settingsProject = new URLSearchParams(location.search).get("settings");
if (settingsProject) {
  openProjectSettings(settingsProject, {
    modalHost,
    onClose: closeModal,
    onSaved: render,
  }).catch(console.error);
}
if (!new URLSearchParams(location.search).has("static")) {
  subscribe("/api/library/events", () => render().catch(console.error));
}
